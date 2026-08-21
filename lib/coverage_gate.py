#!/usr/bin/env python3
"""覆盖率门控(设计文档 §13 / §14.4):阈值判定。

指标与硬阈值(P1 阻断):
- changed_line: 增量行覆盖率 < 60% → 阻断
- new_file:     新文件覆盖率 < 50% → 阻断
- delta_drop:   整体覆盖率下降 > 5% → 阻断
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "coverage-config.json"

DEFAULT_THRESHOLDS = {
    "changed_line": 60,
    "new_file": 50,
    "delta_drop": 5,
}


def load_coverage_config() -> dict:
    """从 config/coverage-config.json 读取硬阈值;缺失或 disabled 时回退默认值。"""
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if data.get("enabled", True):
            return data.get("hard_threshold", DEFAULT_THRESHOLDS)
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_THRESHOLDS


def check_coverage(report: dict, thresholds: Optional[dict] = None) -> dict:
    """report 形如 {"changed_line": 55.0, "new_file": None, "delta_drop": 1.2}。

    值为 None 表示该指标不适用,跳过判定。返回 {"ok", "problems", "thresholds"}。
    阈值优先用传入的 thresholds,否则从 config/coverage-config.json 加载。
    """
    t = {**load_coverage_config(), **(thresholds or {})}
    problems = []

    cl = report.get("changed_line")
    if cl is not None and cl < t["changed_line"]:
        problems.append(f"增量行覆盖率 {cl}% < {t['changed_line']}%")

    nf = report.get("new_file")
    if nf is not None and nf < t["new_file"]:
        problems.append(f"新文件覆盖率 {nf}% < {t['new_file']}%")

    dd = report.get("delta_drop")
    if dd is not None and dd > t["delta_drop"]:
        problems.append(f"整体覆盖率下降 {dd}% > {t['delta_drop']}%")

    return {"ok": not problems, "problems": problems, "thresholds": t}
