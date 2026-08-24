#!/usr/bin/env python3
"""代码评审聚合:双审查员 + 四源聚合 + merge gate(对齐 super-assistant codex-code-review)。

四源:主审(main)、副审(secondary)、变更分析(diff)、覆盖率(coverage)。
聚合:合并 issues、去重、按严重度排序、计算 merge gate。
"""
from __future__ import annotations

from typing import Dict, List

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "Nit": 3}


def aggregate(main_review: dict, secondary_review: dict, diff_summary: dict, coverage_report: dict) -> dict:
    """四源聚合。review 形如 {issues: [{severity, check, description, file}], ...}。"""
    issues: List[dict] = []
    for source, review in (("main", main_review), ("secondary", secondary_review)):
        for issue in review.get("issues", []):
            issues.append({**issue, "source": source})

    # 去重(severity + description 相同视为重复)
    seen = set()
    deduped = []
    for issue in issues:
        key = (issue.get("severity"), issue.get("description"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)

    deduped.sort(key=lambda i: SEVERITY_ORDER.get(i.get("severity"), 99))

    severity_counts: Dict[str, int] = {}
    for i in deduped:
        sev = i.get("severity", "Nit")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "issues": deduped,
        "severity_counts": severity_counts,
        "coverage": coverage_report,
        "diff": diff_summary,
    }


def merge_gate(aggregated: dict, coverage_ok: bool = True) -> dict:
    """merge gate:存在 P0/P1 或覆盖率不达标 → Blocked。"""
    has_blocker = any(i.get("severity") in ("P0", "P1") for i in aggregated.get("issues", []))
    blocked = has_blocker or not coverage_ok
    return {"gate": "Blocked" if blocked else "Ready", "blocked": blocked}


def review(main_review: dict, secondary_review: dict, diff_summary: dict, coverage_report: dict, coverage_ok: bool = True) -> dict:
    """端到端:聚合 + merge gate。"""
    agg = aggregate(main_review, secondary_review, diff_summary, coverage_report)
    gate = merge_gate(agg, coverage_ok)
    return {**agg, **gate}


if __name__ == "__main__":
    import json
    import sys
    demo = review(
        {"issues": [{"severity": "P1", "description": "契约漂移", "file": "a.ts"}]},
        {"issues": [{"severity": "P1", "description": "契约漂移", "file": "a.ts"}, {"severity": "P2", "description": "命名不清晰", "file": "b.ts"}]},
        {"changed_files": 2},
        {"changed_line": 55.0},
        coverage_ok=False,
    )
    print(json.dumps(demo, ensure_ascii=False, indent=2))
    sys.exit(1 if demo["blocked"] else 0)
