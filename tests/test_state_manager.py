#!/usr/bin/env python3
"""state_manager 自测(M0)。运行:python3 tests/test_state_manager.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from state_manager import (  # noqa: E402
    actionable_stages,
    init_state,
    read_state,
    set_stage_output,
    set_stage_state,
    summary,
)


def _tmp_state(tmp: str) -> Path:
    return Path(tmp) / "state.json"


def test_init_and_resume():
    with tempfile.TemporaryDirectory() as d:
        sf = _tmp_state(d)
        init_state(sf, "change-1")
        state = read_state(sf)
        assert state["change_id"] == "change-1"
        assert len(state["stages"]) == 12, len(state["stages"])
        # 初始可推进:仅 Stage 0(无前置)
        assert actionable_stages(sf) == ["0"], actionable_stages(sf)


def test_advance_and_parallel():
    with tempfile.TemporaryDirectory() as d:
        sf = _tmp_state(d)
        init_state(sf, "change-2")
        # 串行推进 0→1→2→3→4
        for sid in ["0", "1", "2", "3", "4"]:
            set_stage_state(sf, sid, "completed")
        # Stage 4 后,5A 与 5B 并行可推进
        assert actionable_stages(sf) == ["5A", "5B"], actionable_stages(sf)
        # 只完成 5A,Stage 6 仍被 5B 阻塞
        set_stage_state(sf, "5A", "completed")
        assert actionable_stages(sf) == ["5B"], actionable_stages(sf)
        # 完成 5B,Stage 6 汇合放行
        set_stage_state(sf, "5B", "completed")
        assert actionable_stages(sf) == ["6"], actionable_stages(sf)


def test_outputs_and_summary():
    with tempfile.TemporaryDirectory() as d:
        sf = _tmp_state(d)
        init_state(sf, "change-3")
        set_stage_output(sf, "2", "openapi_contract", "contracts/api.yaml")
        state = read_state(sf)
        assert state["stages"]["2"]["outputs"]["openapi_contract"] == "contracts/api.yaml"
        s = summary(sf)
        assert s["total"] == 12 and s["done"] == 0
        assert s["actionable"] == ["0"]


def main():
    test_init_and_resume()
    test_advance_and_parallel()
    test_outputs_and_summary()
    print("OK: state_manager 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
