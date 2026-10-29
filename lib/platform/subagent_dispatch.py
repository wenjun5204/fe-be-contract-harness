#!/usr/bin/env python3
"""Subagent 派发适配层(P2-2)——「launch agent → 回传 StageResult → 调 transition」的平台侧落地。

runner 签发 dispatch directive 后,真实平台(Claude Code / OpenClaw 等)需要:
1. 把 directive 翻译成平台可执行的子 Agent 任务(角色提示 + 上下文 + 凭据 + 完成路径);
2. 子 Agent 干完活回传 StageResult(outputs / evidence / receipt);
3. 经唯一 transition 门控推进阶段 —— 绝不直接写 state.json。

本模块提供两个入口(全部确定性、mock 可测):

    build_subagent_task(directive, state_file)  →  平台无关的任务包(prompt 内嵌
        transition CLI 序列;CLI 模式:子 Agent 自己跑命令,hooks 守卫其行为)
    apply_stage_result(state_file, payload)    →  回调模式:平台进程内回传
        StageResult,适配器代为 register → start → complete(与 llm_dispatch
        同一门控语义,TransitionError 收敛为 gate_blocked + hint)

设计红线(与 HARNESS_UPGRADE 三条红线一致):
- 终态唯一入口:本模块不写 state.json,一切终态经 lib/transition;
- fail-closed:receipt/outputs 不合法即 gate_blocked,不伪造终态;
- prompt 中显式告知子 Agent「绝不要直接编辑 state.json」。

用法:
    python3 lib/platform/subagent_dispatch.py task --directive directive.json --state state.json
    python3 lib/platform/subagent_dispatch.py result --state state.json --payload payload.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# 使 `python3 lib/platform/subagent_dispatch.py` 直接执行时也能 import lib.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.delegation import register_receipt  # noqa: E402
from lib.transition import TransitionError, complete_stage, start_stage  # noqa: E402

TASK_SCHEMA = "subagent-task/v1"
HARNESS_ROOT = Path(__file__).resolve().parent.parent.parent


def _role_prompt(subagent: str, harness_root: Path) -> Optional[str]:
    """读取 agents/<subagent>/prompt.md 的角色提示;缺失返回 None(冷启动不阻断)。"""
    path = harness_root / "agents" / subagent / "prompt.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def build_subagent_task(
    directive: dict,
    state_file: str | Path,
    harness_root: Optional[str | Path] = None,
) -> dict:
    """把 dispatch directive 翻译成平台无关的子 Agent 任务包。

    返回 {"schema": "subagent-task/v1", "stage", "subagent", "prompt",
    "required_outputs", "receipt", "context", ...}。平台适配器取 prompt 注入
    子 Agent 上下文,保留 receipt 在回传时使用(README「真实平台适配器应」五步)。
    """
    root = Path(harness_root) if harness_root else HARNESS_ROOT
    stage = directive["stage"]
    subagents = directive.get("subagents") or (
        [directive["subagent"]] if directive.get("subagent") else []
    )
    receipt = directive["receipt"]

    from lib.workflow_fsm import WorkflowFSM
    required_outputs = WorkflowFSM().required_outputs(stage)

    role = _role_prompt(subagents[0], root) if subagents else None
    context = directive.get("context") or {}
    context_text = context.get("text") or f"stage={stage}, contract={directive.get('contract')}"

    receipt_json = json.dumps(receipt, ensure_ascii=False)
    state_arg = str(state_file)
    lines = [
        f"你是 fe-be-contract-harness 的子 Agent: {', '.join(subagents)}。",
        f"当前阶段: Stage {stage}。",
        f"本阶段必需产出(required_outputs,缺一不可): {', '.join(required_outputs) or '无'}。",
        "",
        "## 角色职责",
        role or f"(未找到 {subagents[0]} 的 prompt.md,按阶段要求自行履职)",
        "",
        "## 任务上下文(dispatch context)",
        context_text,
        "",
        "## 完成方式(唯一合法路径)",
        "绝不要直接编辑 state.json。一切阶段推进必须经 lib/transition.py 门控:",
        f"1. python3 lib/transition.py register {state_arg} --receipt '{receipt_json}'",
        f"2. python3 lib/transition.py start {state_arg} {stage}",
        "3. 完成实体工作后,提交产出与证据:",
        f"   python3 lib/transition.py complete {state_arg} {stage} \\",
        f"     --receipt '{receipt_json}' \\",
        "     --outputs '<outputs JSON,键名覆盖 required_outputs>' \\",
        "     --evidence '[{\"type\": \"...\", \"detail\": \"...\"}]'",
        "说明:complete 若被门控拦截,按报错附带的 hint 修正后带同 receipt 重调;"
        "本阶段若带 checkpoint,会停在 checkpoint_pending,人工 approve 后才进终态。",
    ]

    return {
        "schema": TASK_SCHEMA,
        "stage": stage,
        "subagent": subagents[0] if len(subagents) == 1 else None,
        "subagents": subagents,
        "prompt": "\n".join(lines),
        "required_outputs": required_outputs,
        "receipt": receipt,
        "context": context,
        "contract": directive.get("contract"),
        "state_file": state_arg,
        "harness_root": str(root),
    }


def apply_stage_result(
    state_file: str | Path,
    payload: dict,
) -> dict:
    """回调模式:平台回传 StageResult,适配器经 transition 门控推进阶段。

    payload 形态(与标准 envelope 字段一致):
        {"stage", "receipt", "outputs", "evidence"?, "checkpoint_decision"?}
    返回与 llm_dispatch 同构:{"ok": True, "status": ...} 或
    {"ok": False, "status": "blocked"|"gate_blocked", "reasons": [...]}。
    任何不合法都收敛为失败结果,不炸调用方,不写旁路状态。
    """
    sf = Path(state_file)
    stage = payload.get("stage")
    receipt = payload.get("receipt")
    outputs = payload.get("outputs")
    if not stage:
        return {"ok": False, "status": "blocked", "reasons": ["payload 缺少 stage"]}
    # fail-closed:receipt 必须与 payload 阶段一致,防张冠李戴
    if not receipt or receipt.get("stage") != stage:
        return {"ok": False, "status": "blocked",
                "reasons": [f"receipt 缺失或 stage 不匹配(payload={stage}, receipt={receipt and receipt.get('stage')})"]}

    try:
        register_receipt(sf, receipt)  # 幂等:同 stage+token 重复登记覆盖
    except ValueError as e:
        return {"ok": False, "status": "blocked", "reasons": [str(e)]}

    try:
        start_stage(sf, stage)
    except TransitionError:
        pass  # 已 running(子 Agent 自己 start 过)→ 直接走 complete

    evidence = payload.get("evidence") or [{
        "type": "platform_result",
        "detail": f"subagent={receipt.get('subagent') or receipt.get('subagents')}",
    }]
    try:
        res = complete_stage(
            sf, stage,
            outputs=outputs,
            receipt=receipt,
            checkpoint_decision=payload.get("checkpoint_decision"),
            evidence=evidence,
        )
    except TransitionError as e:
        # 门控拦截:附 hint(带同 receipt 重调 complete,勿重启 start)
        suggestion = None
        try:
            from lib.transition import hint as transition_hint
            for s in transition_hint(sf).get("suggestions", []):
                if s.get("stage") == stage:
                    suggestion = s.get("command") or s.get("action")
                    break
        except Exception:  # noqa: BLE001 —— hint 失败不影响拦截记录
            pass
        return {"ok": False, "status": "gate_blocked", "reasons": list(getattr(e, "reasons", [str(e)])),
                **({"hint": suggestion} if suggestion else {})}

    return {"ok": True, "stage": stage, "status": res.get("status") or res.get("state")}


def main(argv=None) -> int:
    import argparse

    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="子 Agent 派发适配(directive ⇄ StageResult)")
    sub = p.add_subparsers(dest="cmd")

    t = sub.add_parser("task", help="dispatch directive → 平台子 Agent 任务包")
    t.add_argument("--directive", help="directive JSON 文件")
    t.add_argument("--directive-json", help="directive JSON 字符串")
    t.add_argument("--state", default="state.json")
    t.add_argument("--harness-root", default=None)

    r = sub.add_parser("result", help="平台回传 StageResult → 经 transition 门控推进")
    r.add_argument("--state", default="state.json")
    r.add_argument("--payload", help="StageResult JSON 文件")
    r.add_argument("--payload-json", help="StageResult JSON 字符串")

    args = p.parse_args(argv)
    if args.cmd == "task":
        directive = _load_json_arg(args.directive, args.directive_json, "--directive")
        task = build_subagent_task(directive, args.state, args.harness_root)
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "result":
        payload = _load_json_arg(args.payload, args.payload_json, "--payload")
        res = apply_stage_result(args.state, payload)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1
    p.print_help()
    return 1


def _load_json_arg(file_arg: Optional[str], inline_arg: Optional[str], flag: str) -> dict:
    if file_arg:
        return json.loads(Path(file_arg).read_text(encoding="utf-8"))
    if inline_arg:
        return json.loads(inline_arg)
    raise SystemExit(f"缺少 {flag}(JSON 文件路径或 JSON 字符串)")


if __name__ == "__main__":
    sys.exit(main())
