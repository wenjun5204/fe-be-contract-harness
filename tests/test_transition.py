#!/usr/bin/env python3
"""transition 唯一入口自测(第一阶段 + 防伪):FSM/前置/产出/receipt 登记/checkpoint/evidence 全门控闭环。

运行:python3 tests/test_transition.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.delegation import consume_receipt, issue_receipt, register_receipt  # noqa: E402
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


def _reg(sf: Path, receipt: dict) -> dict:
    """登记 receipt(模拟主 Agent 委派时的登记动作)。"""
    return register_receipt(sf, receipt)


def test_start_complete_no_checkpoint():
    """Stage 0 无 checkpoint:start + complete 正常完成,evidence/receipt 落盘。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        r = issue_receipt("0", "orchestrator/init", "tok-0")
        _reg(sf, r)
        res = complete_stage(
            sf, "0",
            outputs={"execution_plan": "plan"},
            receipt=r,
            evidence=[{"type": "contract", "detail": "x.yaml", "at": "t0"}],
        )
        assert res["ok"] and res["status"] == "completed", res
        st = read_state(sf)["stages"]["0"]
        assert st["state"] == "completed"
        assert st["receipt"]["subagent"] == "orchestrator/init"
        assert st["evidence"][0]["type"] == "contract"
        assert st["completed_at"]
        # receipt 已消费(一次性)
        assert read_state(sf)["receipts"]["0"]["used"] is True
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
    """产出缺失 / receipt 缺失 / 未登记 / token 伪造 / subagent 不匹配 → 拒绝完成。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        good = issue_receipt("0", "orchestrator/init", "tok-0")
        # 未登记(伪造 receipt,登记表为空时即被拒)
        fake = issue_receipt("0", "orchestrator/init", "attacker-token")
        try:
            complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=fake)
            assert False, "未登记 receipt 应阻断"
        except TransitionError as e:
            assert "未登记" in " ".join(e.reasons), e.reasons
        # 产出缺失(即使 receipt 已登记)
        _reg(sf, good)
        try:
            complete_stage(sf, "0", outputs={}, receipt=good)
            assert False, "产出缺失应阻断"
        except TransitionError as e:
            assert "缺少必需产出" in str(e), e
        # receipt 缺失
        try:
            complete_stage(sf, "0", outputs={"execution_plan": "plan"})
            assert False, "receipt 缺失应阻断"
        except TransitionError as e:
            assert "缺少 dispatch receipt" in str(e), e
        # token 与登记不符(伪造)
        wrong = issue_receipt("0", "orchestrator/init", "another-token")
        try:
            complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=wrong)
            assert False, "token 不符应阻断"
        except TransitionError as e:
            assert "token 与登记不符" in " ".join(e.reasons), e.reasons
        # subagent 不匹配(复制登记 receipt 改 subagent,token 相同)
        wrong_sub = dict(good, subagent="wrong/agent")
        try:
            complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=wrong_sub)
            assert False, "subagent 不匹配应阻断"
        except TransitionError as e:
            assert "subagent 不匹配" in " ".join(e.reasons), e.reasons
        # 正确 receipt 完成
        res = complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=good)
        assert res["status"] == "completed", res


def test_receipt_replay_rejected():
    """消费后重放同一 receipt → 拒绝(一次性防重放)。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        r0 = issue_receipt("0", "orchestrator/init", "t0")
        _reg(sf, r0)
        complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=r0)
        # Stage 1 进入 checkpoint_pending(此时 receipt 未消费)
        start_stage(sf, "1")
        outputs1 = {"requirements_doc": "d", "requirements_spec": _requirements_spec(),
                    "requirements_quality_gate": "p", "requirements_confirmation_status": "c"}
        r1 = issue_receipt("1", "orchestrator/requirements-analyst", "t1")
        _reg(sf, r1)
        complete_stage(sf, "1", outputs=outputs1, receipt=r1)  # -> checkpoint_pending
        # 模拟同一 receipt 已被别处消费(重放场景)
        consume_receipt(sf, "1")
        try:
            complete_stage(sf, "1", outputs=outputs1, receipt=r1, checkpoint_decision="approve")
            assert False, "已消费 receipt 重放应阻断"
        except TransitionError as e:
            assert "已被消费" in " ".join(e.reasons), e.reasons


def test_checkpoint_flow():
    """mandatory_review 阶段:无 decision → checkpoint_pending;approve → completed;revise → running。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        # 打通 0 → 1
        start_stage(sf, "0")
        r0 = issue_receipt("0", "orchestrator/init", "t0")
        _reg(sf, r0)
        complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=r0)
        start_stage(sf, "1")
        outputs1 = {
            "requirements_doc": "doc",
            "requirements_spec": _requirements_spec(),
            "requirements_quality_gate": "pass",
            "requirements_confirmation_status": "confirmed",
        }
        r1 = issue_receipt("1", "orchestrator/requirements-analyst", "t1")
        _reg(sf, r1)
        # 无 decision → checkpoint_pending(receipt 未消费)
        res = complete_stage(sf, "1", outputs=outputs1, receipt=r1)
        assert res["status"] == "checkpoint_pending", res
        assert read_state(sf)["stages"]["1"]["state"] == "checkpoint_pending"
        assert read_state(sf)["receipts"]["1"]["used"] is False
        # approve → completed
        res = complete_stage(sf, "1", outputs=outputs1, receipt=r1, checkpoint_decision="approve")
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
    """mandatory_review revise → 回到 running,不进入终态、不消费 receipt。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        r0 = issue_receipt("0", "orchestrator/init", "t0")
        _reg(sf, r0)
        complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=r0)
        start_stage(sf, "1")
        outputs1 = {"requirements_doc": "doc", "requirements_spec": _requirements_spec(),
                    "requirements_quality_gate": "pass", "requirements_confirmation_status": "confirmed"}
        r1 = issue_receipt("1", "orchestrator/requirements-analyst", "t1")
        _reg(sf, r1)
        res = complete_stage(sf, "1", outputs=outputs1, receipt=r1, checkpoint_decision="revise")
        assert res["ok"] is False and res["status"] == "revise", res
        assert read_state(sf)["stages"]["1"]["state"] == "running"
        assert read_state(sf)["receipts"]["1"]["used"] is False
        # revise 后可重新完成
        res = complete_stage(sf, "1", outputs=outputs1, receipt=r1, checkpoint_decision="approve")
        assert res["status"] == "completed", res


def test_skip_mandatory_requires_approval():
    """mandatory_review 跳过必须 reason + approved_by + 已登记 receipt。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _setup(d)
        start_stage(sf, "0")
        r0 = issue_receipt("0", "orchestrator/init", "t0")
        _reg(sf, r0)
        complete_stage(sf, "0", outputs={"execution_plan": "plan"}, receipt=r0)
        # 无批准
        try:
            skip_stage(sf, "1", reason="", approved_by="")
            assert False, "无批准跳过应阻断"
        except TransitionError as e:
            assert "必须提供 reason 与 approved_by" in str(e), e
        # 有批准但未登记 receipt
        r1 = issue_receipt("1", "orchestrator/requirements-analyst", "t1")
        try:
            skip_stage(sf, "1", reason="契约已提供", approved_by="runner:auto", receipt=r1)
            assert False, "未登记 receipt 跳过应阻断"
        except TransitionError as e:
            assert "未登记" in " ".join(e.reasons), e.reasons
        # 有批准 + 登记 receipt
        _reg(sf, r1)
        res = skip_stage(sf, "1", reason="契约已提供", approved_by="runner:auto", receipt=r1)
        assert res["state"] == "skipped", res
        st = read_state(sf)["stages"]["1"]
        assert st["skip"]["approved_by"] == "runner:auto"
        # skipped 是终态,2 可推进;receipt 已消费
        assert actionable_stages(sf) == ["2"], actionable_stages(sf)
        assert read_state(sf)["receipts"]["1"]["used"] is True


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


def main():
    test_start_complete_no_checkpoint()
    test_prereq_blocked()
    test_outputs_and_receipt_gates()
    test_receipt_replay_rejected()
    test_checkpoint_flow()
    test_checkpoint_revise()
    test_skip_mandatory_requires_approval()
    test_fail_retry()
    print("OK: transition 闭环自测通过(8 组断言)")


if __name__ == "__main__":
    main()
