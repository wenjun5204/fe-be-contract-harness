#!/usr/bin/env python3
"""确定性路径规划自测。运行:python3 tests/test_planner.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.planner.planner import plan  # noqa: E402


def test_plan_default():
    p = plan({})
    assert p["stages"]["1"] == "run" and p["stages"]["2"] == "run"
    assert p["stages"]["6"] == "run" and p["stages"]["9"] == "run"  # 汇合点
    assert p["fast_path"] is False


def test_plan_with_contract():
    p = plan({"has_contract": True})
    assert p["stages"]["1"] == "skip" and p["stages"]["2"] == "skip"
    assert p["stages"]["6"] == "run"  # 汇合点永不可跳过


def test_plan_complexity():
    p = plan({"complexity": "L"})
    assert p["fast_path"] is True


def main():
    test_plan_default()
    test_plan_with_contract()
    test_plan_complexity()
    print("OK: planner 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
