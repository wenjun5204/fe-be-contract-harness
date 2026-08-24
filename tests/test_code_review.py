#!/usr/bin/env python3
"""代码评审聚合自测。运行:python3 tests/test_code_review.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.code_review import aggregate, merge_gate, review  # noqa: E402


def test_aggregate_dedupe():
    main_review = {"issues": [{"severity": "P1", "description": "契约漂移", "file": "a.ts"}]}
    secondary_review = {"issues": [
        {"severity": "P1", "description": "契约漂移", "file": "a.ts"},  # 与主审重复
        {"severity": "P2", "description": "命名不清晰", "file": "b.ts"},
    ]}
    agg = aggregate(main_review, secondary_review, {"changed_files": 2}, {"changed_line": 55.0})
    # 去重:3 条 issue → 2 条
    assert len(agg["issues"]) == 2, agg["issues"]
    assert agg["severity_counts"] == {"P1": 1, "P2": 1}, agg["severity_counts"]
    # P1 排最前
    assert agg["issues"][0]["severity"] == "P1"


def test_merge_gate():
    agg = {"issues": [{"severity": "P1", "description": "x"}]}
    assert merge_gate(agg, coverage_ok=True)["gate"] == "Blocked"
    agg = {"issues": [{"severity": "P2", "description": "x"}]}
    assert merge_gate(agg, coverage_ok=True)["gate"] == "Ready"
    # 覆盖率不达标也 Blocked
    assert merge_gate({"issues": []}, coverage_ok=False)["gate"] == "Blocked"


def test_review_end_to_end():
    r = review(
        {"issues": []},
        {"issues": [{"severity": "Nit", "description": "命名", "file": "x"}]},
        {"changed_files": 1},
        {"changed_line": 75.0},
        coverage_ok=True,
    )
    assert r["gate"] == "Ready" and not r["blocked"]


def main():
    test_aggregate_dedupe()
    test_merge_gate()
    test_review_end_to_end()
    print("OK: code_review 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
