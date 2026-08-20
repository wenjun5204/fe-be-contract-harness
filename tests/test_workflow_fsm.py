#!/usr/bin/env python3
"""workflow_fsm 确定性自测(M0)。

运行:
    python3 tests/test_workflow_fsm.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from workflow_fsm import WorkflowFSM, StageState  # noqa: E402


def test_transitions():
    fsm = WorkflowFSM()
    ok, nxt = fsm.validate_transition(StageState.PENDING, "start")
    assert ok and nxt is StageState.RUNNING, (ok, nxt)

    ok, nxt = fsm.validate_transition(StageState.RUNNING, "complete")
    assert ok and nxt is StageState.COMPLETED, (ok, nxt)

    # 非法转换:COMPLETED 不能再 start
    ok, nxt = fsm.validate_transition(StageState.COMPLETED, "start")
    assert not ok and nxt is None, (ok, nxt)

    # 字符串入参兼容
    ok, nxt = fsm.validate_transition("running", "fail")
    assert ok and nxt is StageState.FAILED, (ok, nxt)


def test_required_outputs():
    fsm = WorkflowFSM()
    ok, missing = fsm.validate_completion("2", {"openapi_contract": "contracts/api.yaml"})
    assert ok, missing

    ok, missing = fsm.validate_completion("2", {})
    assert not ok and "openapi_contract" in missing, missing


def test_parallel_join():
    fsm = WorkflowFSM()
    # Stage 6 是汇合点:前置 5A/5B 都完成才放行
    assert fsm.is_join("6")
    assert fsm.prereqs("6") == ["5A", "5B"], fsm.prereqs("6")

    ok, waiting = fsm.all_prereqs_completed("6", {"5A": "completed", "5B": "completed"})
    assert ok, waiting

    ok, waiting = fsm.all_prereqs_completed("6", {"5A": "completed", "5B": "running"})
    assert not ok and "5B" in waiting, waiting


def test_graph_topology():
    fsm = WorkflowFSM()
    assert fsm.next_stages("4") == ["5A", "5B"], fsm.next_stages("4")
    assert fsm.next_stages("6") == ["7", "8"], fsm.next_stages("6")
    assert fsm.prereqs("9") == ["7", "8"], fsm.prereqs("9")
    assert fsm.checkpoint_type("2") == "mandatory_review"
    assert fsm.checkpoint_type("4") == "none"
    assert fsm.required_outputs("2") == ["openapi_contract"]


def main():
    test_transitions()
    test_required_outputs()
    test_parallel_join()
    test_graph_topology()
    print("OK: workflow_fsm 自测通过(4 组断言)")


if __name__ == "__main__":
    main()
