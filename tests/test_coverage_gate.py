#!/usr/bin/env python3
"""覆盖率门控自测。运行:python3 tests/test_coverage_gate.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.coverage_gate import check_coverage  # noqa: E402


def test_pass():
    r = check_coverage({"changed_line": 75.0, "new_file": 80.0, "delta_drop": 0.0})
    assert r["ok"], r


def test_fail_line():
    r = check_coverage({"changed_line": 45.0})
    assert not r["ok"] and any("增量行覆盖率" in p for p in r["problems"])


def test_fail_drop():
    r = check_coverage({"delta_drop": 8.0})
    assert not r["ok"] and any("下降" in p for p in r["problems"])


def test_none_skipped():
    r = check_coverage({"changed_line": None, "new_file": None, "delta_drop": None})
    assert r["ok"], r


def main():
    test_pass()
    test_fail_line()
    test_fail_drop()
    test_none_skipped()
    print("OK: coverage_gate 自测通过(4 组断言)")


if __name__ == "__main__":
    main()
