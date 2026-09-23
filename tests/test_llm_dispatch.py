#!/usr/bin/env python3
"""LLM 阶段执行器(tool calling 主循环)自测。运行:python3 tests/test_llm_dispatch.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.delegation import issue_receipt  # noqa: E402
from lib.llm_client import MockLLMClient  # noqa: E402
from lib.llm_dispatch import run_llm_stage  # noqa: E402
from lib.state_manager import init_state, read_state, set_stage_state  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CONTRACT = REPO / "examples" / "petstore.yaml"
SUBAGENT = "quality/test-case-generator"


def _directive(token="dispatch-test"):
    receipt = issue_receipt("8", SUBAGENT, token)
    return {
        "stage": "8",
        "subagent": SUBAGENT,
        "subagents": [SUBAGENT],
        "receipt": receipt,
        "contract": str(CONTRACT),
        "context": {"text": "stage=8; contract=petstore; entities=Pet"},
    }


def _state_with_prereqs(d):
    """构造前置阶段(0..6)已终态的 state,使 Stage 8 可 start。"""
    sf = Path(d) / "state.json"
    init_state(sf, "dispatch-test")
    for sid in ("0", "1", "2", "3", "4", "5A", "5B", "6"):
        set_stage_state(sf, sid, "completed")
    return sf


def test_stage_completes_with_tool_calls():
    """模型先检索知识再 report_outputs → 阶段经全门控 completed,receipt 一次性消费。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        script = [
            {"tool_calls": [{"name": "query_knowledge", "arguments": {"domain": "qa"}}]},
            {"tool_calls": [{"name": "read_contract", "arguments": {}}]},
            {"tool_calls": [{"name": "report_outputs",
                             "arguments": {"outputs": {"test_cases": [{"id": "TC-1", "name": "创建订单"}]}}}]},
        ]
        res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert res["ok"], res
        assert res["status"] == "completed", res
        assert res["tool_call_count"] == 3
        state = read_state(sf)
        assert state["stages"]["8"]["state"] == "completed"
        assert state["stages"]["8"]["outputs"]["test_cases"][0]["id"] == "TC-1"
        assert state["receipts"]["8"]["used"] is True  # 一次性消费
        ev = state["stages"]["8"]["evidence"][0]
        assert ev["type"] == "llm_dispatch" and "tool_calls=3" in ev["detail"]


def test_checkpoint_pending_without_auto_approve():
    """artifact_review 阶段未提供决策 → 停在 checkpoint_pending(不伪造终态)。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        script = [
            {"tool_calls": [{"name": "report_outputs",
                             "arguments": {"outputs": {"test_cases": [{"id": "TC-1"}]}}}]},
        ]
        res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=False)
        assert res["ok"] and res["status"] == "checkpoint_pending", res
        assert read_state(sf)["stages"]["8"]["state"] == "checkpoint_pending"


def test_fail_closed_no_report_outputs():
    """模型不调用 report_outputs(连续两轮空转)→ failed,阶段留在 running。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        script = [
            {"content": "我分析了契约,工作已完成"},
            {"content": "我认为不需要调用工具"},
        ]
        res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert not res["ok"] and res["status"] == "failed", res
        assert "空转" in res["reasons"][0]
        assert read_state(sf)["stages"]["8"]["state"] == "running"


def test_max_turns_exhausted():
    """超过 max_turns 仍未收尾 → failed(fail-closed)。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        script = [{"tool_calls": [{"name": "read_contract", "arguments": {}}]} for _ in range(5)]
        res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, max_turns=3, auto_approve=True)
        assert not res["ok"] and res["status"] == "failed", res
        assert "max_turns" in res["reasons"][0]


def test_gate_blocked_on_missing_required_outputs():
    """report_outputs 缺 required_outputs 键 → complete_stage 门控拦截,不伪造终态。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        script = [
            {"tool_calls": [{"name": "report_outputs",
                             "arguments": {"outputs": {"wrong_key": "没有 test_cases"}}}]},
        ]
        res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert not res["ok"] and res["status"] == "gate_blocked", res
        assert any("test_cases" in r for r in res["reasons"]), res["reasons"]
        assert read_state(sf)["stages"]["8"]["state"] == "running"


def test_blocked_when_prereq_not_ready():
    """前置(Stage 6)未终态 → start 被真实阻断。"""
    with tempfile.TemporaryDirectory() as d:
        sf = Path(d) / "state.json"
        init_state(sf, "dispatch-test")  # 什么都不完成
        script = [{"tool_calls": [{"name": "report_outputs",
                                   "arguments": {"outputs": {"test_cases": [1]}}}]}]
        res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert not res["ok"] and res["status"] == "blocked", res
        assert "前置" in res["reasons"][0]


def test_tool_error_self_correction():
    """工具返回 ok=false 不炸循环;模型可依据 error 纠错后继续。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        script = [
            {"tool_calls": [{"name": "query_knowledge", "arguments": {}}]},  # 缺 domain → ok=false
            {"tool_calls": [{"name": "query_knowledge", "arguments": {"domain": "qa"}}]},
            {"tool_calls": [{"name": "report_outputs",
                             "arguments": {"outputs": {"test_cases": [{"id": "TC-2"}]}}}]},
        ]
        res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert res["ok"] and res["status"] == "completed", res


def main():
    test_stage_completes_with_tool_calls()
    test_checkpoint_pending_without_auto_approve()
    test_fail_closed_no_report_outputs()
    test_max_turns_exhausted()
    test_gate_blocked_on_missing_required_outputs()
    test_blocked_when_prereq_not_ready()
    test_tool_error_self_correction()
    print("OK: llm_dispatch 自测通过(7 组断言)")


if __name__ == "__main__":
    main()
