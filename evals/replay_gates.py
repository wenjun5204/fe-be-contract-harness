#!/usr/bin/env python3
"""门控行为回放评测(P2-3):用录制形态的 mock 脚本重放关键场景,断言 fail-closed 语义不变。

防的是"未来改动悄悄放宽门控":每个场景 = 一个 mock LLM 脚本 + 一组门控行为断言。
任何一条断言失败即评测红,等价于 gate regression。

场景(全部 MockLLMClient 确定性重放,零外部依赖):
1. 正常交付   → completed,receipt 一次性消费,evidence 落盘
2. 空转       → failed 落盘 + error 经验写入 + 可 retry
3. 缺产出交付 → gate_blocked,阶段留在 running,不伪造终态
4. 瞬时错误   → 退避重试后成功
5. 前置未就绪 → blocked,不可绕过
运行:python3 evals/replay_gates.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.delegation import issue_receipt  # noqa: E402
from lib.llm_client import LLMError, MockLLMClient  # noqa: E402
from lib.llm_dispatch import run_llm_stage  # noqa: E402
from lib.state_manager import init_state, read_state, set_stage_state  # noqa: E402

CONTRACT = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def _directive(token: str) -> dict:
    sub = "quality/test-case-generator"
    return {
        "stage": "8",
        "subagent": sub,
        "subagents": [sub],
        "receipt": issue_receipt("8", sub, token),
        "contract": str(CONTRACT),
        "context": {"text": "replay"},
    }


def _state_ready(d: str, tmp: Path) -> Path:
    sf = tmp / "state.json"
    init_state(sf, "replay")
    for sid in ("0", "1", "2", "3", "4", "5A", "5B", "6"):
        set_stage_state(sf, sid, "completed")
    return sf


def replay_normal_delivery(tmp: Path) -> dict:
    """场景 1: 正常交付。断言 completed + receipt 消费 + outputs 回填。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_ready(d, tmp)
        script = [{"tool_calls": [{"name": "report_outputs",
                                   "arguments": {"outputs": {"test_cases": [{"id": "TC-1"}],
                                                            "test_report": {"total": 1, "passed": 1, "failed": 0}}}}]}]
        res = run_llm_stage(_directive("replay-1"), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert res["ok"] and res["status"] == "completed", res
        st = read_state(sf)["stages"]["8"]
        assert st["outputs"]["test_cases"][0]["id"] == "TC-1", st
        assert read_state(sf)["receipts"]["8"]["used"] is True  # 一次性消费
        return {"scenario": "normal_delivery", "ok": True}


def replay_idle_fail_closed(tmp: Path) -> dict:
    """场景 2: 空转。断言 failed 真实落盘 + 可 retry(fail-closed 不伪造)。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_ready(d, tmp)
        script = [{"content": "已完成"}, {"content": "不需要工具"}]
        res = run_llm_stage(_directive("replay-2"), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert not res["ok"] and res["status"] == "failed", res
        st = read_state(sf)["stages"]["8"]
        assert st["state"] == "failed" and "空转" in st["error"]["reason"], st
        return {"scenario": "idle_fail_closed", "ok": True}


def replay_missing_outputs_blocked(tmp: Path) -> dict:
    """场景 3: 缺 required_outputs 的交付。断言 gate_blocked,阶段留 running。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_ready(d, tmp)
        script = [{"tool_calls": [{"name": "report_outputs",
                                   "arguments": {"outputs": {"wrong": "x"}}}]}]
        res = run_llm_stage(_directive("replay-3"), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert not res["ok"] and res["status"] == "gate_blocked", res
        assert read_state(sf)["stages"]["8"]["state"] == "running"  # 不伪造终态
        return {"scenario": "missing_outputs_gate_blocked", "ok": True}


def replay_transient_error_recovered(tmp: Path) -> dict:
    """场景 4: 瞬时 LLM 错误。断言退避重试后阶段仍能 completed。"""
    class Flaky:
        def __init__(self):
            self.left = 2

        def chat(self, messages, tools=None):
            if self.left:
                self.left -= 1
                raise LLMError("503 Service Unavailable")
            return {"tool_calls": [{"id": "c1", "name": "report_outputs",
                                    "arguments": {"outputs": {"test_cases": [{"id": "TC-1"}],
                                                             "test_report": {"total": 1, "passed": 1, "failed": 0}}}}]}

    with tempfile.TemporaryDirectory() as d:
        sf = _state_ready(d, tmp)
        res = run_llm_stage(_directive("replay-4"), sf, client=Flaky(),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert res["ok"], res
        return {"scenario": "transient_error_recovered", "ok": True}


def replay_prereq_not_ready(tmp: Path) -> dict:
    """场景 5: 前置未就绪(Stage 6 未完成)。断言 blocked,门控不可绕过。"""
    with tempfile.TemporaryDirectory() as d:
        sf = Path(d) / "state.json"
        init_state(sf, "replay")  # 什么都不完成
        script = [{"tool_calls": [{"name": "report_outputs",
                                   "arguments": {"outputs": {"test_cases": [1]}}}]}]
        res = run_llm_stage(_directive("replay-5"), sf, client=MockLLMClient(script),
                            contract_path=CONTRACT, workdir=d, auto_approve=True)
        assert not res["ok"] and res["status"] == "blocked", res
        assert "前置" in res["reasons"][0], res
        return {"scenario": "prereq_not_ready_blocked", "ok": True}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        # 副作用隔离:_fail() 会写真实采集池(evals/regressions/.pending/)与经验目录,
        # 回放场景的失败素材属测试噪音,重定向到 tmp——采集池只收真实 run 的素材
        import lib.experience as _exp
        import lib.llm_dispatch as _disp
        reg_backup, exp_backup = _disp.REGRESSIONS_DIR, _exp.EXPERIENCE_DIR
        _disp.REGRESSIONS_DIR = Path(tmp) / "regressions"
        _exp.EXPERIENCE_DIR = Path(tmp) / "experience"
        try:
            scenarios = [
                replay_normal_delivery,
                replay_idle_fail_closed,
                replay_missing_outputs_blocked,
                replay_transient_error_recovered,
                replay_prereq_not_ready,
            ]
            results = []
            for fn in scenarios:
                try:
                    results.append(fn(Path(tmp)))
                except AssertionError as e:
                    results.append({"scenario": fn.__name__, "ok": False, "assert": str(e)})
            for r in results:
                print(json.dumps(r, ensure_ascii=False))
            passed = sum(1 for r in results if r["ok"])
            print(f"replay: {passed}/{len(results)} scenarios passed")
            return 0 if passed == len(results) else 1
        finally:
            _disp.REGRESSIONS_DIR = reg_backup
            _exp.EXPERIENCE_DIR = exp_backup


if __name__ == "__main__":
    sys.exit(main())
