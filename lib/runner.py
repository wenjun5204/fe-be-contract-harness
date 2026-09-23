#!/usr/bin/env python3
"""编排 runner —— 确定性主循环:按 DAG 驱动 12 阶段(设计文档 §15「主 Agent 只调度」)。

第一阶段:任何阶段到达终态必须经 lib/transition(FSM + 前置 + 产出 + receipt +
checkpoint + evidence 全门控)。runner 不再直接写 state.json。

- 确定性阶段(0 / 5A / 5B / 6 / 10)真实执行,经 transition 完成
- LLM 阶段(3 / 4 / 7 / 8 / 9)签发委派指令(dispatch directive),不完成
- --auto 演示模式:LLM 阶段显式带批准跳过(record skip),checkpoint 自动 approve
- 非 auto 模式:checkpoint 阶段停在 checkpoint_pending;前置未就绪的推进会被
  transition 真实阻断(不可绕过的体现)
- --live 模式:LLM 阶段经 tool calling 主循环真实执行(lib/llm_dispatch),
  运行时可选 openai(OpenAI 兼容网关)或 mock(脚本驱动,演示/测试)

用法:
    python3 lib/runner.py run <contract> --out <dir> [--state <state.json>] [--stacks react,vue,node,java] [--auto]
    python3 lib/runner.py run <contract> --out gen --live --llm-runtime mock --llm-script script.json --auto
    python3 lib/runner.py status [--state <state.json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# 使 `python3 lib/runner.py` 直接执行时也能 import lib.* 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.consistency import cross_stack_check  # noqa: E402
from lib.contract.generator import write_out  # noqa: E402
from lib.contract.parser import parse_contract  # noqa: E402
from lib.contract.verify import verify  # noqa: E402
from lib.context_orchestrator import build_dispatch_context  # noqa: E402
from lib.delegation import issue_receipt, load_policy, resolve_subagents  # noqa: E402
from lib.state_manager import actionable_stages, init_state, summary  # noqa: E402
from lib.transition import TransitionError, complete_stage, skip_stage, start_stage  # noqa: E402

# 确定性阶段(可直接执行)vs LLM 阶段(签发委派指令)
DETERMINISTIC = {"0", "5A", "5B", "6", "10"}

# 演示模式(契约已提供)下跳过的 LLM 阶段及其理由
SKIP_STAGES = {
    "1": ("orchestrator/requirements-analyst", "契约已提供(输入即契约),需求以契约为准"),
    "2": ("contract/contract-designer", "契约已提供(输入即契约),契约设计以契约为准"),
    "3": ("orchestrator/services-analyst", "演示模式:单仓库,不产技术方案"),
    "4": ("orchestrator/git-client", "演示模式:单仓库本地开发,不新建分支"),
    "7": ("quality/code-review", "演示模式:无真实 PR 评审"),
    "8": ("quality/test-case-generator", "演示模式:无真实测试用例"),
    "9": ("orchestrator/deployer", "演示模式:无真实提测部署"),
}


def _change_id(contract: Path) -> str:
    return contract.stem


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stage_subagents(stage: str, policy: dict, stacks: Optional[List[str]] = None, *, for_skip: bool = False) -> List[str]:
    """解析阶段本次实际执行（或跳过确认）的 Agent。"""
    subagents = resolve_subagents(stage, stacks, policy, for_skip=for_skip)
    if not subagents:
        raise ValueError(f"阶段 {stage} 未解析到可用 subagent")
    return subagents


def _directive(
    stage: str,
    policy: dict,
    contract: str,
    entities: Optional[List[str]] = None,
    repo: Optional[str | Path] = None,
    context_max_tokens: int = 4000,
) -> dict:
    """为 LLM 阶段生成包含受预算知识上下文的委派指令。"""
    subagents = _stage_subagents(stage, policy)
    receipt = issue_receipt(stage, subagents, token="runner")
    context = build_dispatch_context(stage, contract, entities, repo, context_max_tokens)
    return {
        "stage": stage,
        "subagent": subagents[0] if len(subagents) == 1 else None,
        "subagents": subagents,
        "receipt": receipt,
        "contract": contract,
        "context": context,
        "note": f"需要 {', '.join(subagents)} 执行(LLM 阶段,runner 仅签发委派)",
    }


def _register(state_file: Path, receipt: dict) -> dict:
    """签发后登记 receipt 到 state(防伪造;complete/skip 前必须登记)。"""
    from lib.delegation import register_receipt
    register_receipt(state_file, receipt)
    return receipt


def _try_transition(state_file: Path, fn, events: List[dict], stage: str, kind: str, detail: str) -> Optional[dict]:
    """执行一个经 transition 的动作;失败记录 blocked 事件。"""
    try:
        res = fn()
        status = res.get("status") or res.get("state")
        events.append({"stage": stage, "kind": kind, "detail": detail, "status": status})
        return res
    except TransitionError as e:
        events.append({"stage": stage, "kind": "blocked", "detail": f"{detail} -> {e}"})
        return None


def _start_then_complete(state_file: Path, stage: str, **kwargs) -> dict:
    """start(前置校验)→ complete(产出/receipt/checkpoint 门控)的顺序执行。"""
    start_stage(state_file, stage)
    return complete_stage(state_file, stage, **kwargs)


def _build_stage_client(llm_runtime: str, llm_script: Optional[str | Path], stage: str):
    """为某个 LLM 阶段构造运行时客户端。mock 脚本支持 {"stages": {<stage>: [...]}} 分阶段。"""
    if llm_runtime == "openai":
        from lib.llm_client import OpenAICompatClient
        return OpenAICompatClient()
    if llm_runtime == "mock":
        from lib.llm_client import MockLLMClient
        if not llm_script:
            raise ValueError("--live --llm-runtime mock 需要 --llm-script(JSON 脚本)")
        data = json.loads(Path(llm_script).read_text(encoding="utf-8"))
        steps = data.get("stages", {}).get(stage) if isinstance(data, dict) else data
        if steps is None:
            raise ValueError(f"mock 脚本缺少阶段 {stage} 的步骤(stages.{stage})")
        return MockLLMClient(steps)
    raise ValueError(f"未知 llm-runtime: {llm_runtime}(可选 mock / openai)")


def _run_llm_stage(
    state_file: Path,
    sid: str,
    policy: dict,
    contract: Path,
    entities: List[str],
    repo: Optional[str | Path],
    context_max_tokens: int,
    *,
    live: bool,
    llm_runtime: str,
    llm_script: Optional[str | Path],
    llm_max_turns: int,
    auto: bool,
    events: List[dict],
) -> None:
    """LLM 阶段统一入口:默认仅签发 directive;--live 时经 tool calling 循环真实执行。"""
    directive = _directive(sid, policy, str(contract), entities, repo, context_max_tokens)
    if not live:
        events.append({"stage": sid, "kind": "agent", "detail": directive})
        return
    from lib.llm_dispatch import run_llm_stage
    res = run_llm_stage(
        directive, state_file,
        client=_build_stage_client(llm_runtime, llm_script, sid),
        contract_path=contract,
        workdir=repo or Path.cwd(),
        max_turns=llm_max_turns,
        auto_approve=auto,
    )
    events.append({"stage": sid, "kind": "llm", "detail": res})


def run(
    contract: str | Path,
    out_dir: str | Path,
    state_file: str | Path,
    stacks: List[str],
    auto: bool = False,
    repo: Optional[str | Path] = None,
    context_max_tokens: int = 4000,
    live: bool = False,
    llm_runtime: str = "mock",
    llm_script: Optional[str | Path] = None,
    llm_max_turns: int = 12,
) -> dict:
    contract = Path(contract)
    state_file = Path(state_file)
    policy = load_policy()
    contract_model = parse_contract(contract)
    entities = sorted(contract_model.get("schemas", {}).keys())

    # Stage 0: 初始化
    if not state_file.exists():
        init_state(state_file, _change_id(contract))

    events: List[dict] = []

    def record(stage: str, kind: str, detail) -> None:
        events.append({"stage": stage, "kind": kind, "detail": detail})

    # ---- Stage 0: 初始化(确定性) ----
    _try_transition(
        state_file,
        lambda: _start_then_complete(
            state_file, "0",
            outputs={"execution_plan": f"contract-driven SDLC: {contract.name}"},
            receipt=_register(state_file, issue_receipt("0", "orchestrator/init", "runner")),
            evidence=[{"type": "contract", "detail": str(contract), "at": _now()}],
        ),
        events, "0", "done", "初始化 state(经 transition 门控)",
    )

    # ---- Stage 1/2/3/4: 契约已提供 → LLM 阶段 ----
    for sid in ("1", "2", "3", "4"):
        if auto and not live:
            sub, reason = SKIP_STAGES[sid]
            _try_transition(
                state_file,
                lambda sid=sid, sub=sub, reason=reason: skip_stage(
                    state_file, sid,
                    reason=reason,
                    approved_by="runner:auto",
                    receipt=_register(state_file, issue_receipt(sid, sub, "runner")),
                    evidence=[{"type": "contract", "detail": str(contract), "at": _now()}],
                ),
                events, sid, "skip", reason,
            )
        else:
            _run_llm_stage(
                state_file, sid, policy, contract, entities, repo, context_max_tokens,
                live=live, llm_runtime=llm_runtime, llm_script=llm_script,
                llm_max_turns=llm_max_turns, auto=auto, events=events,
            )

    # ---- Stage 5A/5B: codegen(确定性) ----
    backend = [s for s in stacks if s in ("node", "java")]
    frontend = [s for s in stacks if s in ("react", "vue")]
    for sid, group in (("5A", backend), ("5B", frontend)):
        if not group:
            subagents = _stage_subagents(sid, policy, for_skip=True)
            _try_transition(
                state_file,
                lambda sid=sid, subagents=subagents: skip_stage(
                    state_file, sid,
                    reason="无该端技术栈",
                    approved_by="runner:auto",
                    receipt=_register(state_file, issue_receipt(sid, subagents, "runner", action="skip")),
                ),
                events, sid, "skip", "无该端技术栈",
            )
            continue
        try:
            files = []
            for s in group:
                written = write_out(contract, s, Path(out_dir) / s)
                verify(contract, s)  # G1 生成门
                files.extend(f"{s}/{f}" for f in written)
            _try_transition(
                state_file,
                lambda sid=sid, files=files, group=group: _start_then_complete(
                    state_file, sid,
                    outputs={
                        "changed_files": files,
                        "coverage": "G1 verified(骨架生成,演示模式未跑真实覆盖率)",
                    },
                    receipt=_register(state_file, issue_receipt(sid, _stage_subagents(sid, policy, group), "runner")),
                    checkpoint_decision="approve" if auto else None,
                    evidence=[{"type": "codegen", "detail": f"{sid}: {', '.join(group)}", "at": _now()}],
                ),
                events, sid, "done", f"codegen + G1 门:{', '.join(group)}",
            )
        except Exception as e:  # codegen 本身失败
            record(sid, "failed", f"codegen 异常: {e}")

    # ---- Stage 6: 一致性(确定性) ----
    try:
        r = cross_stack_check(contract)
        _try_transition(
            state_file,
            lambda: _start_then_complete(
                state_file, "6",
                outputs={"consistency_report": json.dumps(r, ensure_ascii=False)},
                receipt=_register(state_file, issue_receipt("6", "contract/consistency-checker", "runner")),
                checkpoint_decision="approve" if auto else None,
                evidence=[{"type": "consistency", "detail": f"ok={r['ok']}", "at": _now()}],
            ),
            events, "6", "done", f"跨栈一致性: {r['ok']}",
        )
    except Exception as e:
        record("6", "failed", f"一致性检查异常: {e}")

    # ---- Stage 7/8/9: LLM 阶段 ----
    for sid in ("7", "8", "9"):
        if auto and not live:
            sub, reason = SKIP_STAGES[sid]
            _try_transition(
                state_file,
                lambda sid=sid, sub=sub, reason=reason: skip_stage(
                    state_file, sid,
                    reason=reason,
                    approved_by="runner:auto",
                    receipt=_register(state_file, issue_receipt(sid, sub, "runner")),
                ),
                events, sid, "skip", reason,
            )
        else:
            _run_llm_stage(
                state_file, sid, policy, contract, entities, repo, context_max_tokens,
                live=live, llm_runtime=llm_runtime, llm_script=llm_script,
                llm_max_turns=llm_max_turns, auto=auto, events=events,
            )

    # ---- Stage 10: 交付报告(确定性) ----
    _try_transition(
        state_file,
        lambda: _start_then_complete(
            state_file, "10",
            outputs={"delivery_report": f"交付报告(见 summary): {contract.name}"},
            receipt=_register(state_file, issue_receipt("10", "orchestrator/notifier", "runner")),
            checkpoint_decision="approve" if auto else None,
            evidence=[{"type": "delivery", "detail": "runner 汇总", "at": _now()}],
        ),
        events, "10", "done", "交付报告(见 summary)",
    )

    return {
        "ok": True,
        "contract": str(contract),
        "state": str(state_file),
        "summary": summary(state_file),
        "events": events,
        "next_actionable": actionable_stages(state_file),
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="fe-be-contract-harness 编排 runner")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="按 DAG 驱动工作流(经唯一 transition 门控)")
    r.add_argument("contract")
    r.add_argument("--out", default="gen")
    r.add_argument("--state", default="state.json")
    r.add_argument("--stacks", default="react,vue,node,java")
    r.add_argument("--auto", action="store_true", help="演示自动模式(LLM 阶段显式跳过 + checkpoint 自动批准)")
    r.add_argument("--repo", default=None, help="目标仓库路径；用于向 LLM 阶段注入相关仓库知识")
    r.add_argument("--context-max-tokens", type=int, default=4000, help="单次委派的知识上下文 token 预算")
    r.add_argument("--live", action="store_true", help="LLM 阶段真实执行(tool calling 主循环,而非仅签发 directive)")
    r.add_argument("--llm-runtime", default="mock", choices=["mock", "openai"], help="LLM 运行时:mock=脚本驱动,openai=OpenAI 兼容网关")
    r.add_argument("--llm-script", default=None, help="mock 运行时脚本(JSON,支持 stages.<stage> 分阶段步骤数组)")
    r.add_argument("--llm-max-turns", type=int, default=12, help="单阶段 tool calling 最大轮次")

    s = sub.add_parser("status", help="查看状态")
    s.add_argument("--state", default="state.json")

    args = p.parse_args(argv)

    if args.cmd == "run":
        stacks = [x.strip() for x in args.stacks.split(",") if x.strip()]
        result = run(
            args.contract, args.out, args.state, stacks, auto=args.auto, repo=args.repo,
            context_max_tokens=args.context_max_tokens, live=args.live,
            llm_runtime=args.llm_runtime, llm_script=args.llm_script,
            llm_max_turns=args.llm_max_turns,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    elif args.cmd == "status":
        print(json.dumps(summary(Path(args.state)), ensure_ascii=False, indent=2))
        return 0
    else:
        p.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
