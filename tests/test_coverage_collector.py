#!/usr/bin/env python3
"""覆盖率采集适配器自测(解析部分确定性)。运行:python3 tests/test_coverage_collector.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.coverage_collector import parse_line_coverage, parse_report  # noqa: E402


def test_parse_vitest():
    out = "File | % Stmts | % Branch | % Funcs | % Lines\nAll files | 80 | 70 | 90 | 85.5"
    assert parse_line_coverage(out) == 85.5


def test_parse_istanbul():
    assert parse_line_coverage("Lines: 72.3%") == 72.3


def test_parse_none():
    assert parse_line_coverage("no coverage here") is None


def test_parse_report():
    r = parse_report("vitest", "All files | 80 | 70 | 90 | 55.0")
    assert r["changed_line"] == 55.0
    assert r["new_file"] is None and r["delta_drop"] is None


def main():
    test_parse_vitest()
    test_parse_istanbul()
    test_parse_none()
    test_parse_report()
    print("OK: coverage_collector 自测通过(4 组断言)")


if __name__ == "__main__":
    main()
