#!/usr/bin/env python3
"""transition 唯一入口自测(第一阶段):FSM/前置/产出/receipt/checkpoint/evidence 全门控闭环。

运行:python3 tests/test_transition.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.delegation import issue_receipt  # noqa: E402
from lib.state_manager import actionable_stages, init_state, read_state  # noqa: E402
from lib.transition import (  # noqa: E402
    TransitionError,
    complete_stage,
    fail_stage,
    retry_stage,
    skip_stage,
    start_stage,
)


def _setup(tmp: str, change: str = "t") -> Path:
    sf = Path(tmp) / "state.json"
    init_state(sf, change)
    return sf


def test_start_complete_no_checkpoint():
    """Stage 0 无 checkpoint:start + complete 正常完成,evidence/receipt 落盘。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        res = complete_stage(
            sf, "0",
            outputs={"execution_plan": "plan"},
            receipt=issue_receipt("0", "orchestrator/init", "tok"),
            evidence=[{"type": "contract", "detail": "x.yaml", "at": "t0"}],
        )
        assert res["ok"] and res["status"] == "completed", res
        st = read_state(sf)["stages"]["0"]
        assert st["state"] == "completed"
        assert st["receipt"]["subagent"] == "orchestrator/init"
        assert st["evidence"][0]["type"] == "contract"
        assert st["completed_at"]
        # 终态不可再次 complete
        try:
            complete_stage(sf, "0", outputs={"execution_plan": "plan"})
            assert False, "终态应拒绝再次 complete"
        except TransitionError:
            pass


def test_prereq_blocked():
    """前置未终态时 start 被阻断(不可绕过)。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        try:
            start_stage(sf, "1")  # 前置 0 未完成
            assert False, "前置未就绪应阻断"
        except TransitionError as e:
            assert "前置未就绪" in str(e), e


def test_outputs_and_receipt_gates():
    """产出缺失 / receipt 缺失 / subagent 不匹配 → 拒绝完成。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        for sid in ["0"]:
            start_stage(sf, sid)
        # 产出缺失
        try:
            complete_stage(sf, "0", outputs={}, receipt=issue_receipt("0", "orchestrator/init", "t"))
            assert False, "产出缺失应阻断"
        except TransitionError as e:
            assert "缺少必需产出" in str(e), e
        # receipt 缺失
        try:
            complete_stage(sf, "0", outputs={"execution_plan": "plan"})
            assert False, "receipt 缺失应阻断"
        except TransitionError as e:
            assert "缺少 dispatch receipt" in str(e), e
        # subagent 不匹配
        try:
            complete_stage(
                sf, "0",
                outputs={"execution_plan": "plan"},
                receipt=issue_receipt("0", "wrong/agent", "t"),
            )
            assert False, "subagent 不匹配应阻断"
        except TransitionError as e:
            assert "subagent 不匹配" in " ".join(e.reasons), e.reasons


def _requirements_spec() -> dict:
    """构造通过 Stage 1 SDD 门控的最小结构化需求 Spec。"""
    categories = [
        "goal_value", "users_permissions", "scope", "main_flow", "state",
        "data", "exceptions", "interaction", "dependencies", "non_functional", "acceptance",
    ]
    return {
        "schema_version": "1.0",
        "status": "approved",
        "scope": {"complexity": "M", "subsystems": [], "cross_team_dependencies": [],
                  "split_required": False, "split_decision": None},
        "clarification": {
            "round": 1, "max_rounds": 3, "questions": [], "answers": [],
            "confirmed_facts": [], "assumptions": [], "unresolved_questions": [],
            "coverage": {c: "covered" for c in categories},
        },
        "contract_readiness": {
            "entities": [{"name": "Pet", "fields": [{"name": "id", "type": "integer", "required": True}], "states": []}],
            "error_codes": [{"code": "404", "meaning": "not found"}],
        },
        "document": {"approved": True, "quality_gate": "passed"},
    }


def test_checkpoint_flow():
    """mandatory_review 阶段:无 decision → checkpoint_pending;approve → completed;revise → running。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        # 打通 0 → 1
        start_stage(sf, "0")
        complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=issue_receipt("0", "orchestrator/init", "t"))
        start_stage(sf, "1")
        outputs1 = {
            "requirements_doc": "doc",
            "requirements_spec": _requirements_spec(),
            "requirements_quality_gate": "pass",
            "requirements_confirmation_status": "confirmed",
        }
        # 无 decision → checkpoint_pending
        res = complete_stage(
            sf, "1", outputs=outputs1,
            receipt=issue_receipt("1", "orchestrator/requirements-analyst", "t"),
        )
        assert res["status"] == "checkpoint_pending", res
        assert read_state(sf)["stages"]["1"]["state"] == "checkpoint_pending"
        # approve → completed
        res = complete_stage(
            sf, "1", outputs=outputs1,
            receipt=issue_receipt("1", "orchestrator/requirements-analyst", "t"),
            checkpoint_decision="approve",
        )
        assert res["status"] == "completed", res
        st = read_state(sf)["stages"]["1"]
        assert st["checkpoint"]["decision"] == "approve"
        # 已终态不可再 complete
        try:
            complete_stage(sf, "1", outputs=outputs1, checkpoint_decision="approve")
            assert False
        except TransitionError:
            pass


def test_checkpoint_revise():
    """mandatory_review revise → 回到 running,不进入终态。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=issue_receipt("0", "orchestrator/init", "t"))
        start_stage(sf, "1")
        outputs1 = {"requirements_doc": "doc", "requirements_spec": _requirements_spec(),
                    "requirements_quality_gate": "pass", "requirements_confirmation_status": "confirmed"}
        res = complete_stage(
            sf, "1", outputs=outputs1,
            receipt=issue_receipt("1", "orchestrator/requirements-analyst", "t"),
            checkpoint_decision="revise",
        )
        assert res["ok"] is False and res["status"] == "revise", res
        assert read_state(sf)["stages"]["1"]["state"] == "running"
        # revise 后可重新完成
        res = complete_stage(
            sf, "1", outputs=outputs1,
            receipt=issue_receipt("1", "orchestrator/requirements-analyst", "t"),
            checkpoint_decision="approve",
        )
        assert res["status"] == "completed", res


def test_skip_mandatory_requires_approval():
    """mandatory_review 跳过必须 reason + approved_by + receipt。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=issue_receipt("0", "orchestrator/init", "t"))
        # 无批准
        try:
            skip_stage(sf, "1", reason="", approved_by="")
            assert False, "无批准跳过应阻断"
        except TransitionError as e:
            assert "必须提供 reason 与 approved_by" in str(e), e
        # 有批准 + receipt
        res = skip_stage(
            sf, "1",
            reason="契约已提供",
            approved_by="runner:auto",
            receipt=issue_receipt("1", "orchestrator/requirements-analyst", "t"),
        )
        assert res["state"] == "skipped", res
        st = read_state(sf)["stages"]["1"]
        assert st["skip"]["approved_by"] == "runner:auto"
        # skipped 是终态,2 可推进
        assert actionable_stages(sf) == ["2"], actionable_stages(sf)


def test_fail_retry():
    """fail → failed;retry → running。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        fail_stage(sf, "0", reason="boom")
        assert read_state(sf)["stages"]["0"]["state"] == "failed"
        assert read_state(sf)["stages"]["0"]["error"]["reason"] == "boom"
        retry_stage(sf, "0")
        assert read_state(sf)["stages"]["0"]["state"] == "running"


def main():
    test_start_complete_no_checkpoint()
    test_prereq_blocked()
    test_outputs_and_receipt_gates()
    test_checkpoint_flow()
    test_checkpoint_revise()
    test_skip_mandatory_requires_approval()
    test_fail_retry()
    print("OK: transition 闭环自测通过(7 组断言)")


if __name__ == "__main__":
    main()
