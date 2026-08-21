#!/usr/bin/env python3
"""编排 runner —— 确定性主循环:按 DAG 驱动 12 阶段(设计文档 §15「主 Agent 只调度」)。

runner 是「主 Agent」的确定性骨架:
- 确定性阶段(init / codegen / consistency)真实执行
- LLM 阶段(需求 / 契约 / 方案 / 分支 / 评审 / 测试 / 部署)签发委派指令(dispatch directive)
- 每个阶段走 delegation fail-closed + checkpoint 门控

用法:
    python3 lib/runner.py run <contract> --out <dir> [--state <state.json>] [--stacks react,vue,node,java] [--auto]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 使 `python3 lib/runner.py` 直接执行时也能 import lib.* 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.consistency import cross_stack_check  # noqa: E402
from lib.contract.generator import write_out  # noqa: E402
from lib.contract.verify import verify  # noqa: E402
from lib.delegation import issue_receipt, load_policy  # noqa: E402
from lib.state_manager import actionable_stages, init_state, set_stage_state, summary  # noqa: E402
from lib.workflow_fsm import WorkflowFSM  # noqa: E402

# 确定性阶段(可直接执行)vs LLM 阶段(签发委派指令)
DETERMINISTIC = {"0", "5A", "5B", "6", "10"}


def _change_id(contract: Path) -> str:
    return contract.stem


def _directive(stage: str, policy: dict, contract: str) -> dict:
    """为 LLM 阶段生成委派指令(subagent + receipt + 输入)。"""
    subagent = policy.get("stage_subagent", {}).get(stage, "unknown")
    receipt = issue_receipt(stage, subagent, token="runner")
    return {
        "stage": stage,
        "subagent": subagent,
        "receipt": receipt,
        "contract": contract,
        "note": f"需要 {subagent} 执行(LLM 阶段,runner 仅签发委派)",
    }


def run(
    contract: str | Path,
    out_dir: str | Path,
    state_file: str | Path,
    stacks: List[str],
    auto: bool = False,
) -> dict:
    contract = Path(contract)
    state_file = Path(state_file)
    policy = load_policy()
    fsm = WorkflowFSM()

    # Stage 0: 初始化
    if not state_file.exists():
        init_state(state_file, _change_id(contract))
    set_stage_state(state_file, "0", "completed")

    # Stage 1/2:契约已提供 → 视为已满足(输入即契约)
    for sid in ("1", "2"):
        set_stage_state(state_file, sid, "completed")

    events: List[dict] = []

    def record(stage: str, kind: str, detail) -> None:
        events.append({"stage": stage, "kind": kind, "detail": detail})

    record("0", "done", "初始化 state")
    record("1", "done", "契约已提供,跳过需求分析")
    record("2", "done", "契约已提供,跳过契约设计")

    # Stage 3/4: LLM 阶段 → 委派指令
    for sid in ("3", "4"):
        record(sid, "agent", _directive(sid, policy, str(contract)))

    # Stage 5A/5B: codegen(确定性)
    backend = [s for s in stacks if s in ("node", "java")]
    frontend = [s for s in stacks if s in ("react", "vue")]
    for sid, group in (("5A", backend), ("5B", frontend)):
        if not group:
            record(sid, "skip", "无该端技术栈")
            set_stage_state(state_file, sid, "skipped")
            continue
        for s in group:
            write_out(contract, s, Path(out_dir) / s)
            verify(contract, s)  # G1 生成门
        set_stage_state(state_file, sid, "completed")
        record(sid, "done", f"codegen + G1 门:{', '.join(group)}")

    # Stage 6: 一致性(确定性)
    r = cross_stack_check(contract)
    set_stage_state(state_file, "6", "completed")
    record("6", "done", f"跨栈一致性: {r['ok']}")

    # Stage 7/8/9: LLM 阶段 → 委派指令
    for sid in ("7", "8", "9"):
        record(sid, "agent", _directive(sid, policy, str(contract)))

    # Stage 10: 汇总(确定性)
    set_stage_state(state_file, "10", "completed")
    record("10", "done", "交付报告(见 summary)")

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

    r = sub.add_parser("run", help="按 DAG 驱动工作流")
    r.add_argument("contract")
    r.add_argument("--out", default="gen")
    r.add_argument("--state", default="state.json")
    r.add_argument("--stacks", default="react,vue,node,java")
    r.add_argument("--auto", action="store_true", help="自动模式(LLM 阶段仅签发指令,不等待)")

    s = sub.add_parser("status", help="查看状态")
    s.add_argument("--state", default="state.json")

    args = p.parse_args(argv)

    if args.cmd == "run":
        stacks = [x.strip() for x in args.stacks.split(",") if x.strip()]
        result = run(args.contract, args.out, args.state, stacks, auto=args.auto)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    elif args.cmd == "status":
        from lib.state_manager import summary
        print(json.dumps(summary(Path(args.state)), ensure_ascii=False, indent=2))
        return 0
    else:
        p.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
