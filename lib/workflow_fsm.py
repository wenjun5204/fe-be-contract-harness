#!/usr/bin/env python3
"""Workflow FSM —— 确定性工作流状态机。

职责:
1. 阶段状态转换校验(单阶段生命周期)
2. 路由计算(完成当前阶段后的下一阶段)
3. 完成合法性校验(required_outputs + checkpoint)
4. 并行支线管理(prereqs / 汇合判定)

设计:纯计算、无状态写入,由 hook 层调用,保持 LLM-as-Master + 确定性守门。
运行:`python3 lib/workflow_fsm.py next 4` 等子命令,详见 --help。
"""
from __future__ import annotations

import argparse
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DAG_PATH = REPO_ROOT / "lib" / "workflow-dag.json"


class StageState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    CHECKPOINT_PENDING = "checkpoint_pending"
    INTERACTION_WAITING = "interaction_waiting"
    CHECKPOINT_CONFIRMED = "checkpoint_confirmed"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


# 单阶段生命周期转换表(与设计文档 §9 一致)
TRANSITIONS = {
    (StageState.PENDING, "start"): StageState.RUNNING,
    (StageState.RUNNING, "complete"): StageState.COMPLETED,
    (StageState.RUNNING, "checkpoint"): StageState.CHECKPOINT_PENDING,
    (StageState.RUNNING, "interact"): StageState.INTERACTION_WAITING,
    (StageState.RUNNING, "fail"): StageState.FAILED,
    (StageState.RUNNING, "skip"): StageState.SKIPPED,
    (StageState.CHECKPOINT_PENDING, "approve"): StageState.COMPLETED,
    (StageState.CHECKPOINT_PENDING, "revise"): StageState.RUNNING,
    (StageState.CHECKPOINT_PENDING, "skip"): StageState.COMPLETED,
    (StageState.INTERACTION_WAITING, "resume"): StageState.RUNNING,
    (StageState.FAILED, "retry"): StageState.RUNNING,
    (StageState.SKIPPED, "force_run"): StageState.RUNNING,
}

# 视为"可进入下游"的终态
TERMINAL = {StageState.COMPLETED, StageState.SKIPPED}


class WorkflowFSM:
    """确定性 FSM:读取 workflow-dag.json,提供转换/完成/汇合校验。"""

    def __init__(self, dag: Optional[dict] = None):
        self.dag = dag if dag is not None else self._load_dag()
        self.stage_graph: Dict[str, dict] = self.dag.get("stage_graph", {})

    @staticmethod
    def _load_dag() -> dict:
        with open(DAG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ---- 图拓扑查询 ----
    def stages(self) -> List[str]:
        return list(self.stage_graph.keys())

    def next_stages(self, stage_id: str) -> List[str]:
        return list(self.stage_graph.get(stage_id, {}).get("next", []))

    def prereqs(self, stage_id: str) -> List[str]:
        """反向边:哪些阶段的 next 指向本阶段(用于并行汇合判定)。"""
        return [
            sid for sid, info in self.stage_graph.items()
            if stage_id in info.get("next", [])
        ]

    def is_join(self, stage_id: str) -> bool:
        return len(self.prereqs(stage_id)) > 1

    def checkpoint_type(self, stage_id: str) -> str:
        return self.stage_graph.get(stage_id, {}).get("checkpoint", "none")

    def required_outputs(self, stage_id: str) -> List[str]:
        return list(self.stage_graph.get(stage_id, {}).get("required_outputs", []))

    # ---- 状态机校验 ----
    def validate_transition(
        self, current, action: str
    ) -> Tuple[bool, Optional[StageState]]:
        if isinstance(current, str):
            current = StageState(current)
        nxt = TRANSITIONS.get((current, action))
        if nxt is None:
            return False, None
        return True, nxt

    def validate_completion(self, stage_id: str, state_data: dict) -> Tuple[bool, List[str]]:
        """校验阶段产出是否满足 required_outputs(非空即视为已产出)。"""
        missing = [k for k in self.required_outputs(stage_id) if not state_data.get(k)]
        return (len(missing) == 0), missing

    @staticmethod
    def _is_done(state_value) -> bool:
        if isinstance(state_value, StageState):
            return state_value in TERMINAL
        return state_value in (StageState.COMPLETED.value, StageState.SKIPPED.value)

    def all_prereqs_completed(self, stage_id: str, state: dict) -> Tuple[bool, List[str]]:
        """并行汇合:所有前置阶段均处于终态才放行;返回未就绪的前置列表。"""
        waiting = [p for p in self.prereqs(stage_id) if not self._is_done(state.get(p))]
        return (len(waiting) == 0), waiting


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="workflow_fsm 确定性状态机")
    sub = parser.add_subparsers(dest="cmd")

    p_next = sub.add_parser("next", help="查询某阶段的下一阶段")
    p_next.add_argument("stage")

    p_pre = sub.add_parser("prereqs", help="查询某阶段的前置阶段(反向边)")
    p_pre.add_argument("stage")

    p_trans = sub.add_parser("transition", help="校验状态转换")
    p_trans.add_argument("state")
    p_trans.add_argument("action")

    args = parser.parse_args(argv)
    fsm = WorkflowFSM()

    if args.cmd == "next":
        print(json.dumps(fsm.next_stages(args.stage), ensure_ascii=False))
    elif args.cmd == "prereqs":
        print(json.dumps(fsm.prereqs(args.stage), ensure_ascii=False))
    elif args.cmd == "transition":
        ok, nxt = fsm.validate_transition(args.state, args.action)
        print(json.dumps({"ok": ok, "next": nxt.value if nxt else None}))
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
