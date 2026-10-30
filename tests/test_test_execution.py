#!/usr/bin/env python3
"""测试执行闭环自测。运行:python3 tests/test_test_execution.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.test_execution import (  # noqa: E402
    build_test_report,
    check_test_report,
    parse_failures,
    parse_test_summary,
)

# jest 输出样例(Test Files + Tests 两行,含失败)
JEST_OUTPUT = """PASS src/api/client.test.ts
FAIL src/types/api.test.ts
  ● Pet › required fields

    expect(received).toBe(expected)

    Object: {"name": 1}

Test Suites: 1 failed, 1 passed, 2 total
Tests:       3 failed, 4 passed, 7 total
Snapshots:   0 total
Time:        2.5 s
"""

# vitest 输出样例(空格分隔,无冒号)
VITEST_OUTPUT = """ ✓ src/api/client.test.ts (3)
 ✗ src/types/api.test.ts (4)

 Test Files  1 failed (2)
      Tests  3 failed | 4 passed (7)
   Start at  ...
"""

# 二进制/无摘要输出(命令没跑起来)
NO_SUMMARY_OUTPUT = """node:command not found
"""


def test_parse_jest_summary():
    s = parse_test_summary(JEST_OUTPUT)
    # 只取 Tests 行语义:7 total, 4 passed, 3 failed
    assert s == {"total": 7, "passed": 4, "failed": 3, "skipped": 0, "parsed": True}, s


def test_parse_vitest_summary():
    s = parse_test_summary(VITEST_OUTPUT)
    assert s["parsed"] is True
    assert s["failed"] == 3, s
    assert s["passed"] == 4, s


def test_parse_no_summary():
    s = parse_test_summary(NO_SUMMARY_OUTPUT)
    assert s["parsed"] is False, s


def test_parse_failures():
    fs = parse_failures(JEST_OUTPUT)
    # "● Pet › required fields" → suite=Pet, case=required fields
    assert any(f.get("suite") == "Pet" and "required" in f["case"] for f in fs), fs


def test_gate_all_green():
    r = {"summary": {"total": 7, "passed": 7, "failed": 0, "skipped": 0, "parsed": True},
         "failed_reasons": []}
    g = check_test_report(r)
    assert g["ok"], g


def test_gate_failed_cases():
    r = {"summary": {"total": 7, "passed": 4, "failed": 3, "skipped": 0, "parsed": True},
         "failed_reasons": []}
    g = check_test_report(r)
    assert not g["ok"] and any("失败用例" in p for p in g["problems"]), g


def test_gate_unparsed_fail_closed():
    # 无摘要 → fail-closed,不能因为"没有失败数字"就放行
    r = {"summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "parsed": False},
         "failed_reasons": ["输出无测试摘要(疑似未跑用例): jest"]}
    g = check_test_report(r)
    assert not g["ok"], g


def test_gate_zero_total_fail_closed():
    # 没有用例被执行(total=0)→ 不能放行("写了用例"≠"跑了用例")
    r = {"summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "parsed": True},
         "failed_reasons": []}
    g = check_test_report(r)
    assert not g["ok"] and any("total=0" in p for p in g["problems"]), g


def test_build_report_aggregates_and_fail_closed():
    # 命令1 正常全绿;命令2 无摘要且退出码非零 → 计入 failed + reasons
    results = [
        {"command": "jest", "exit_code": 0, "output": "Tests: 5 passed, 5 total"},
        {"command": "jest src/other", "exit_code": 1, "output": "boom"},
    ]
    r = build_test_report("node", results)
    assert r["summary"]["passed"] == 5, r
    assert r["summary"]["failed"] == 1, r
    assert r["failed_reasons"], r
    assert not check_test_report(r)["ok"]


def test_build_report_timeout_counts_as_failure():
    results = [{"command": "jest", "timeout": True, "output": ""}]
    r = build_test_report("node", results)
    assert any("超时" in x for x in r["failed_reasons"]), r
    assert not check_test_report(r)["ok"]


def test_build_report_zero_exit_without_summary_suspect():
    # 退出码 0 但无摘要 → 可疑,不放行
    results = [{"command": "jest", "exit_code": 0, "output": "no summary here"}]
    r = build_test_report("node", results)
    assert any("无测试摘要" in x for x in r["failed_reasons"]), r
    assert not check_test_report(r)["ok"]


def main():
    test_parse_jest_summary()
    test_parse_vitest_summary()
    test_parse_no_summary()
    test_parse_failures()
    test_gate_all_green()
    test_gate_failed_cases()
    test_gate_unparsed_fail_closed()
    test_gate_zero_total_fail_closed()
    test_build_report_aggregates_and_fail_closed()
    test_build_report_timeout_counts_as_failure()
    test_build_report_zero_exit_without_summary_suspect()
    print("OK: test_execution 自测通过(11 组断言)")


if __name__ == "__main__":
    main()
