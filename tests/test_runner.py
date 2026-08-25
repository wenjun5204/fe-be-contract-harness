#!/usr/bin/env python3
"""runner 自测(第一阶段):确定性阶段经 transition 完成,LLM 阶段只签发指令,不可绕过。

运行:python3 tests/test_runner.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.runner import run  # noqa: E402
from lib.state_manager import read_state  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def test_auto_mode_completes_loop():
    """--auto:LLM 阶段显式带批准跳过,checkpoint 自动 approve,全部阶段终态,产物落盘。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        r = run(EXAMPLE, out, state, ["node", "react"], auto=True)
        assert r["ok"], r
        # 12 阶段全部终态(completed/skipped)
        assert r["summary"]["done"] == 12, r["summary"]
        assert not r["summary"]["running"] and not r["summary"]["failed"]
        # codegen 产物真实落盘
        assert (out / "node" / "codegen-manifest.json").exists()
        assert (out / "react" / "codegen-manifest.json").exists()
        # 终态全部带审计字段(receipt / completed_at / evidence)
        st = read_state(state)["stages"]
        for sid, s in st.items():
            assert s["state"] in ("completed", "skipped"), (sid, s)
            assert s["completed_at"], (sid, s)
            if s["state"] == "completed":
                assert s["receipt"], (sid, s)
        # 无 blocked 事件
        assert not [e for e in r["events"] if e["kind"] == "blocked"], r["events"]
        # 状态文件可续跑
        assert state.exists()


def test_java_vue_receipts_match_actual_codegen_agents():
    """Java + Vue 时，5A/5B receipt 必须记录对应实际 codegen Agent。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        r = run(EXAMPLE, out, state, ["java", "vue"], auto=True)
        assert r["ok"], r
        st = read_state(state)["stages"]
        assert st["5A"]["receipt"]["subagent"] == "codegen/java-codegen", st["5A"]
        assert st["5B"]["receipt"]["subagent"] == "codegen/vue-codegen", st["5B"]
        assert (out / "java" / "codegen-manifest.json").exists()
        assert (out / "vue" / "codegen-manifest.json").exists()


def test_non_auto_blocks_at_unmet_prereq():
    """非 auto:LLM 阶段仅签发指令;前置未就绪的确定性阶段被 transition 真实阻断。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        r = run(EXAMPLE, out, state, ["node", "react"], auto=False)
        assert r["ok"], r
        # 仅 Stage 0 终态;LLM 阶段(1/2/3/4/7/8/9)签发指令
        assert r["summary"]["done"] == 1, r["summary"]
        agent_stages = {e["stage"] for e in r["events"] if e["kind"] == "agent"}
        assert agent_stages == {"1", "2", "3", "4", "7", "8", "9"}, agent_stages
        # 前置未就绪的推进被阻断(不可绕过)
        blocked = [e["stage"] for e in r["events"] if e["kind"] == "blocked"]
        assert "5A" in blocked and "5B" in blocked and "6" in blocked, blocked
        # 当前可推进:仅 Stage 1(等待需求分析)
        assert r["next_actionable"] == ["1"], r["next_actionable"]
        # 状态机一致:stage 0 completed,其余非终态
        st = read_state(state)["stages"]
        assert st["0"]["state"] == "completed"
        assert st["1"]["state"] == "pending"


def main():
    test_auto_mode_completes_loop()
    test_java_vue_receipts_match_actual_codegen_agents()
    test_non_auto_blocks_at_unmet_prereq()
    print("OK: runner 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
