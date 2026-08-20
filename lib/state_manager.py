#!/usr/bin/env python3
"""状态持久化管理器 —— 读写 pipeline state.json,支持断点续跑与并行汇合调度。

职责:
1. init        —— 按 DAG 初始化全阶段 pending 的 state.json
2. set-state   —— 更新阶段状态(与 workflow_fsm 的转换校验配合使用)
3. set-output  —— 写阶段产出字段(与 required_outputs 校验配合使用)
4. actionable  —— 计算当前可推进的阶段(前置均终态,支持并行分支)
5. summary     —— 进度汇总

设计:JSON 落盘,UTF-8,时间戳 ISO 8601 UTC;与 workflow_fsm.py 共享 workflow-dag.json。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DAG_PATH = REPO_ROOT / "lib" / "workflow-dag.json"

# 使 `python3 lib/state_manager.py` 直接执行时也能以包形式 import lib.*
sys.path.insert(0, str(REPO_ROOT))

# 终态(与 workflow_fsm.py 的 TERMINAL 保持一致)
TERMINAL = {"completed", "skipped"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_dag() -> dict:
    with open(DAG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def init_state(state_file: Path, change_id: str) -> dict:
    """按 DAG 初始化 state.json:所有阶段 pending、产出为空。"""
    dag = load_dag()
    state = {
        "change_id": change_id,
        "workflow_source": "local",
        "current_stage": None,
        "created_at": _now(),
        "updated_at": _now(),
        "stages": {
            sid: {"state": "pending", "outputs": {}, "updated_at": None}
            for sid in dag["stage_graph"]
        },
    }
    write_state(state_file, state)
    return state


def read_state(state_file: Path) -> dict:
    if not state_file.exists():
        raise FileNotFoundError(f"state file not found: {state_file}")
    return json.loads(state_file.read_text(encoding="utf-8"))


def write_state(state_file: Path, state: dict) -> None:
    state["updated_at"] = _now()
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def set_stage_state(state_file: Path, stage_id: str, value: str) -> dict:
    state = read_state(state_file)
    if stage_id not in state["stages"]:
        raise KeyError(f"unknown stage: {stage_id}")
    state["stages"][stage_id]["state"] = value
    state["stages"][stage_id]["updated_at"] = _now()
    state["current_stage"] = stage_id
    write_state(state_file, state)
    return state


def set_stage_output(state_file: Path, stage_id: str, field: str, value: str) -> dict:
    state = read_state(state_file)
    if stage_id not in state["stages"]:
        raise KeyError(f"unknown stage: {stage_id}")
    state["stages"][stage_id]["outputs"][field] = value
    write_state(state_file, state)
    return state


def _stage_states(state: dict) -> dict:
    return {sid: s["state"] for sid, s in state["stages"].items()}


def actionable_stages(state_file: Path) -> List[str]:
    """计算当前可推进的阶段:非终态 + 所有前置均终态(经 FSM 汇合校验)。"""
    state = read_state(state_file)
    from lib.workflow_fsm import WorkflowFSM  # 延迟导入,避免模块加载顺序问题

    fsm = WorkflowFSM()
    st = _stage_states(state)
    out = []
    for sid in fsm.stages():
        if st[sid] in TERMINAL:
            continue
        ok, _ = fsm.all_prereqs_completed(sid, st)
        if ok:
            out.append(sid)
    return out


def summary(state_file: Path) -> dict:
    state = read_state(state_file)
    st = _stage_states(state)
    total = len(state["stages"])
    done = sum(1 for s in st.values() if s in TERMINAL)
    return {
        "change_id": state["change_id"],
        "total": total,
        "done": done,
        "running": [sid for sid, s in st.items() if s == "running"],
        "failed": [sid for sid, s in st.items() if s == "failed"],
        "actionable": actionable_stages(state_file),
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="state_manager 状态持久化")
    sub = p.add_subparsers(dest="cmd")

    s_init = sub.add_parser("init", help="初始化 state.json")
    s_init.add_argument("state_file")
    s_init.add_argument("change_id")

    s_set = sub.add_parser("set-state", help="更新阶段状态")
    s_set.add_argument("state_file")
    s_set.add_argument("stage_id")
    s_set.add_argument("value")

    s_out = sub.add_parser("set-output", help="写阶段产出字段")
    s_out.add_argument("state_file")
    s_out.add_argument("stage_id")
    s_out.add_argument("field")
    s_out.add_argument("value")

    s_act = sub.add_parser("actionable", help="列出当前可推进阶段")
    s_act.add_argument("state_file")

    s_sum = sub.add_parser("summary", help="进度汇总")
    s_sum.add_argument("state_file")

    args = p.parse_args(argv)
    sf = Path(args.state_file)

    if args.cmd == "init":
        init_state(sf, args.change_id)
        print(json.dumps({"ok": True, "file": str(sf)}, ensure_ascii=False))
    elif args.cmd == "set-state":
        set_stage_state(sf, args.stage_id, args.value)
        print(json.dumps({"ok": True}, ensure_ascii=False))
    elif args.cmd == "set-output":
        set_stage_output(sf, args.stage_id, args.field, args.value)
        print(json.dumps({"ok": True}, ensure_ascii=False))
    elif args.cmd == "actionable":
        print(json.dumps(actionable_stages(sf), ensure_ascii=False))
    elif args.cmd == "summary":
        print(json.dumps(summary(sf), ensure_ascii=False, indent=2))
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
