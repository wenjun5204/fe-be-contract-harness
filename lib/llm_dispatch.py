#!/usr/bin/env python3
"""LLM 阶段执行器 —— Tool Calling 主循环 + 结果回填 complete_stage。

把 runner 签发的 dispatch directive 真正跑起来(设计文档 §15「主 Agent 只调度」
的执行层落地):

    directive ──► register_receipt ──► start_stage ──► tool calling 循环
                                                       │  (模型 ⇄ 工具多轮交互)
                         complete_stage ◄── report_outputs(终态工具) ◄──┘

fail-closed 语义(与既有门控完全一致,不新增旁路):
- 循环内模型只能通过工具影响世界;工具执行异常收敛为 {"ok": False} 回给模型自纠错
- 阶段要达终态,必须调用 report_outputs 提交覆盖 required_outputs 的 structured
  outputs,再走 complete_stage 全门控(FSM / receipt / checkpoint / evidence)
- 未调用 report_outputs、超过 max_turns、或模型连续空转 → 阶段停在 running,
  返回 {"ok": False, "status": "failed"}(不伪造完成)

用法(runner --live 内部调用;亦可独立使用):
    from lib.llm_client import MockLLMClient
    from lib.llm_dispatch import run_llm_stage
    res = run_llm_stage(directive, state_file, client=MockLLMClient(script),
                        contract_path="examples/petstore.yaml", auto_approve=True)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from lib.delegation import register_receipt
from lib.llm_client import LLMClient, LLMError
from lib.tool_registry import ToolRegistry, build_default_tools
from lib.transition import TransitionError, complete_stage, start_stage

MAX_TURNS_DEFAULT = 12
NUDGE_MESSAGE = (
    "你没有调用任何工具。请使用可用工具完成本阶段工作,"
    "并最终调用 report_outputs 提交 structured outputs(不调用无法完成阶段)。"
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assistant_message(resp: dict) -> dict:
    """把规范化响应转回 OpenAI wire 格式的 assistant 消息(供多轮上下文)。"""
    tool_calls = [
        {
            "id": tc["id"],
            "type": "function",
            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)},
        }
        for tc in resp.get("tool_calls") or []
    ]
    msg: dict = {"role": "assistant", "content": resp.get("content")}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def _tool_result_message(call_id: str, result: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


def build_system_prompt(directive: dict, required_outputs: List[str]) -> str:
    """构造 subagent 系统提示:角色 + 阶段纪律(fail-closed 前置告知)。"""
    subagents = directive.get("subagents") or ([directive["subagent"]] if directive.get("subagent") else [])
    return (
        f"你是 fe-be-contract-harness 的子 Agent: {', '.join(subagents)}。\n"
        f"当前阶段: Stage {directive['stage']}。\n"
        f"本阶段必需产出(required_outputs,缺一不可): {', '.join(required_outputs) or '无'}。\n"
        "工作纪律:\n"
        "1. 优先调用工具获取事实(契约/知识/文件),不要凭空编造。\n"
        "2. 完成工作后必须调用 report_outputs 提交 structured outputs,"
        "键名覆盖全部 required_outputs;不调用该工具阶段无法完成。\n"
        "3. 工具返回 ok=false 时根据 error 自纠错,不要重复同样的错误调用。\n"
    )


def run_llm_stage(
    directive: dict,
    state_file: str | Path,
    *,
    client: LLMClient,
    contract_path: Optional[str | Path] = None,
    workdir: Optional[str | Path] = None,
    tools: Optional[ToolRegistry] = None,
    max_turns: int = MAX_TURNS_DEFAULT,
    auto_approve: bool = False,
) -> dict:
    """执行一个 LLM 阶段:register → start → tool calling 循环 → complete。

    返回:
    - {"ok": True, "status": "completed"|"skipped"|"checkpoint_pending", ...}
    - {"ok": False, "status": "blocked"|"failed"|"gate_blocked", "reasons": [...]}
      (failed = 模型侧未交付;gate_blocked = complete_stage 门控拦截;均不伪造终态)
    """
    sf = Path(state_file)
    stage = directive["stage"]
    receipt = directive["receipt"]

    from lib.workflow_fsm import WorkflowFSM
    fsm = WorkflowFSM()
    required_outputs = fsm.required_outputs(stage)

    toolset = tools if tools is not None else build_default_tools(
        contract_path=directive.get("contract") or contract_path,
        workdir=workdir,
    )

    # 1. receipt 登记防伪 + start(前置校验)
    try:
        register_receipt(sf, receipt)
        start_stage(sf, stage)
    except (TransitionError, ValueError) as e:
        return {"ok": False, "stage": stage, "status": "blocked", "reasons": [str(e)]}

    # 2. 构造初始消息(system 纪律 + dispatch 上下文)
    context = directive.get("context") or {}
    messages: List[dict] = [
        {"role": "system", "content": build_system_prompt(directive, required_outputs)},
        {"role": "user", "content": context.get("text") or f"stage={stage}, contract={directive.get('contract')}"},
    ]

    transcript: List[dict] = []
    tool_call_count = 0
    outputs: Optional[dict] = None
    nudged = False

    def _fail(reason: str) -> dict:
        return {
            "ok": False, "stage": stage, "status": "failed",
            "reasons": [reason], "transcript": transcript, "tool_call_count": tool_call_count,
        }

    # 3. tool calling 主循环
    for turn in range(1, max_turns + 1):
        try:
            resp = client.chat(messages, toolset.schemas())
        except LLMError as e:
            return _fail(f"LLM 运行时错误: {e}")

        calls = resp.get("tool_calls") or []
        if not calls:
            if nudged:  # 连续两轮无工具调用 → 空转,fail-closed
                return _fail("模型连续两轮未调用工具(疑似空转),阶段未交付")
            nudged = True
            messages.append(_assistant_message(resp))
            messages.append({"role": "user", "content": NUDGE_MESSAGE})
            transcript.append({"turn": turn, "content": resp.get("content"), "nudged": True})
            continue

        messages.append(_assistant_message(resp))
        transcript.append({
            "turn": turn,
            "tool_calls": [{"name": c["name"], "arguments": c["arguments"]} for c in calls],
        })
        for call in calls:
            tool_call_count += 1
            result = toolset.execute(call["name"], call["arguments"])
            messages.append(_tool_result_message(call["id"], result))
            if call["name"] == "report_outputs" and result.get("ok"):
                outputs = call["arguments"].get("outputs")
                break
        if outputs is not None:
            break
    else:
        return _fail(f"超过 max_turns={max_turns} 仍未调用 report_outputs,阶段未交付")

    # 4. 回填 complete_stage(全门控;不过门即 gate_blocked,不伪造终态)
    evidence = [{
        "type": "llm_dispatch",
        "detail": f"tool_calls={tool_call_count}, turns={len(transcript)}, subagent={receipt.get('subagent')}",
        "at": _now(),
    }]
    try:
        res = complete_stage(
            sf, stage,
            outputs=outputs,
            receipt=receipt,
            checkpoint_decision="approve" if auto_approve else None,
            evidence=evidence,
        )
    except TransitionError as e:
        return {
            "ok": False, "stage": stage, "status": "gate_blocked",
            "reasons": e.reasons, "transcript": transcript, "tool_call_count": tool_call_count,
        }

    return {
        "ok": True, "stage": stage, "status": res.get("status") or res.get("state"),
        "outputs": outputs, "transcript": transcript, "tool_call_count": tool_call_count,
    }
