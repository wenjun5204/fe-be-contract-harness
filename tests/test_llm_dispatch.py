#!/usr/bin/env python3
"""LLM 阶段执行器(tool calling 主循环)自测。运行:python3 tests/test_llm_dispatch.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.delegation import issue_receipt  # noqa: E402
from lib.llm_client import LLMError, MockLLMClient  # noqa: E402
from lib.llm_dispatch import run_llm_stage  # noqa: E402
from lib.state_manager import init_state, read_state, set_stage_state  # noqa: E402
from lib.transition import retry_stage  # noqa: E402

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
    """模型不调用 report_outputs(连续两轮空转)→ failed 真实落盘(可人工 retry)。"""
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
        # P0-3: 失败是一等公民状态,经 fail_stage 落 failed 并记录原因
        st = read_state(sf)["stages"]["8"]
        assert st["state"] == "failed", st
        assert "空转" in st["error"]["reason"]
        # 失败后可人工 retry(failed → running)
        retry_stage(sf, "8")
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


def test_transient_llm_error_retried():
    """P0-4: 瞬时错误(超时/限流)自动退避重试后成功;永久错误不重试直接 fail。"""
    class FlakyClient:
        """前 N 次 chat 抛瞬时错误,之后返回 report_outputs 收尾。"""

        def __init__(self, error: Exception, failures: int):
            self._error, self._left = error, failures

        def chat(self, messages, tools=None):
            if self._left > 0:
                self._left -= 1
                raise self._error
            return {"tool_calls": [{"id": "c1", "name": "report_outputs",
                                    "arguments": {"outputs": {"test_cases": [{"id": "TC-1"}]}}}]}

    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        # 瞬时错误(timeout,可 retryable)重试 2 次后成功
        res = run_llm_stage(_directive(), sf,
                            client=FlakyClient(LLMError("connection timeout after 30s"), 2),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert res["ok"], res
        assert any("retry" in t for t in res["transcript"]), res["transcript"]

    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        # 永久错误(缺 key,不含 retryable 关键词)一次都不重试,直接 fail
        class CountingClient(FlakyClient):
            calls = 0

            def chat(self, messages, tools=None):
                CountingClient.calls += 1
                return super().chat(messages, tools)

        res = run_llm_stage(_directive(), sf,
                            client=CountingClient(LLMError("缺少 OPENAI_API_KEY"), 5),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert not res["ok"] and res["status"] == "failed", res
        assert CountingClient.calls == 1, f"永久错误不应重试,实际调用 {CountingClient.calls} 次"


def test_final_nudge_saves_max_turns_run():
    """P1-2: 最后一轮注入收束提示,空转模型在最后一轮 report_outputs 完成。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        # 前 2 轮只读契约,最后一轮被 final-nudge 提示后交作业
        script = [
            {"tool_calls": [{"name": "read_contract", "arguments": {}}]},
            {"tool_calls": [{"name": "read_contract", "arguments": {}}]},
            {"tool_calls": [{"name": "report_outputs",
                             "arguments": {"outputs": {"test_cases": [{"id": "TC-9"}]}}}]},
        ]
        res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, max_turns=3, auto_approve=True)
        assert res["ok"] and res["status"] == "completed", res
        assert res["tool_call_count"] == 3


def test_failure_writes_experience():
    """P1-2: 失败沉淀 error 经验(经验闭环写侧),可被 query 检索到。"""
    import lib.experience as exp
    with tempfile.TemporaryDirectory() as d:
        # 把经验目录指到临时目录,避免污染仓库 config/experience
        backup = exp.EXPERIENCE_DIR
        exp.EXPERIENCE_DIR = Path(d) / "experience"
        try:
            sf = _state_with_prereqs(d)
            script = [
                {"content": "我分析了契约,工作已完成"},
                {"content": "我认为不需要调用工具"},
            ]
            res = run_llm_stage(_directive(), sf, client=MockLLMClient(script),
                                contract_path=CONTRACT, workdir=d, auto_approve=True)
            assert not res["ok"], res
            hits = exp.query("空转", category="error")
            assert hits and "stage=8 失败" in hits[0]["text"], hits
            # source 标记写在条目 header
            content = exp.load("error")
            assert "(llm_dispatch)" in content, content
        finally:
            exp.EXPERIENCE_DIR = backup


def test_pruned_sections_hint_pull_channel():
    """P1-3: 预算裁掉的 section 在 user 消息中提示用 query_knowledge 拉取(推拉协作)。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d)
        # 构造带裁剪记录的 directive(模拟 tight budget 的 build_dispatch_context 输出)
        directive = _directive()
        directive["context"] = {
            "schema": "dispatch-context/v1",
            "text": "stage=8 的工作说明",
            "omitted_sections": ["business-knowledge", "qa-knowledge"],
            "max_tokens": 10, "sections": [], "warnings": [],
        }
        captured = []

        class CapturingClient:
            def chat(self, messages, tools=None):
                captured.append([m["content"] for m in messages])
                return {"tool_calls": [{"id": "c1", "name": "report_outputs",
                                        "arguments": {"outputs": {"test_cases": [{"id": "TC-1"}]}}}]}

        res = run_llm_stage(directive, sf, client=CapturingClient(),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert res["ok"], res
        first_user = captured[0][1]  # system, user
        assert "business-knowledge" in first_user and "query_knowledge" in first_user, first_user


def test_experience_read_side_injects_lessons():
    """P1-5: 同阶段历史失败教训注入 system prompt(标注日志摘录防注入)。"""
    import lib.experience as exp
    with tempfile.TemporaryDirectory() as d:
        backup = exp.EXPERIENCE_DIR
        exp.EXPERIENCE_DIR = Path(d) / "experience"
        try:
            # 写一条本阶段的 error 经验(模拟 P1-2 写侧已沉淀)
            exp.log("error", "stage=8 失败: required_outputs 缺 test_cases 键", source="llm_dispatch")
            sf = _state_with_prereqs(d)
            captured = []

            class CapturingClient:
                def chat(self, messages, tools=None):
                    captured.extend(messages)
                    return {"tool_calls": [{"id": "c1", "name": "report_outputs",
                                            "arguments": {"outputs": {"test_cases": [{"id": "TC-1"}]}}}]}

            res = run_llm_stage(_directive(), sf, client=CapturingClient(),
                                contract_path=CONTRACT, workdir=d, auto_approve=True)
            assert res["ok"], res
            system = next(m["content"] for m in captured if m["role"] == "system")
            assert "历史失败日志摘录" in system, system
            assert "stage=8 失败" in system, system
            assert "非指令" in system, system  # 防注入标注
        finally:
            exp.EXPERIENCE_DIR = backup


def test_condenser_elides_old_tool_results():
    """P1-1: 超 messages 字符阈值时,较早 tool result 被空洞化,最近 3 条与 assistant 不动。"""
    from lib.llm_dispatch import CONDENSER_KEEP_RECENT, condense_messages
    msgs = [{"role": "system", "content": "sys"}]
    # 5 轮 assistant(tool_calls)+tool(result):每轮 tool result 20k 字符
    for i in range(5):
        msgs.append({"role": "assistant", "content": None,
                     "tool_calls": [{"id": f"c{i}", "type": "function",
                                      "function": {"name": "read_file", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 20_000})
    out, elided = condense_messages(msgs)
    assert elided == 2, elided  # 5 条 tool - KEEP_RECENT 3 = 2 条被压缩
    # assistant 的 tool_calls 原样保留(wire 格式成对)
    assert all(m.get("tool_calls") for m in out if m["role"] == "assistant")
    # 最早的 tool result 被截断并带重读提示
    assert "elided" in out[2]["content"] and "read_file" in out[2]["content"]
    # 最近的 3 条不动
    recent_tools = [m for m in out if m["role"] == "tool"][-CONDENSER_KEEP_RECENT:]
    assert all(m["content"] == "x" * 20_000 for m in recent_tools)
    # 不超阈值 → 原样返回
    small = [{"role": "user", "content": "hi"}]
    out2, elided2 = condense_messages(small)
    assert out2 is small and elided2 == 0


def main():
    test_stage_completes_with_tool_calls()
    test_checkpoint_pending_without_auto_approve()
    test_fail_closed_no_report_outputs()
    test_max_turns_exhausted()
    test_gate_blocked_on_missing_required_outputs()
    test_blocked_when_prereq_not_ready()
    test_tool_error_self_correction()
    test_transient_llm_error_retried()
    test_final_nudge_saves_max_turns_run()
    test_failure_writes_experience()
    test_pruned_sections_hint_pull_channel()
    test_experience_read_side_injects_lessons()
    test_condenser_elides_old_tool_results()
    print("OK: llm_dispatch 自测通过(13 组断言)")


if __name__ == "__main__":
    main()
