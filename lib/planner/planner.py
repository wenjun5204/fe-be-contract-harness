#!/usr/bin/env python3
"""确定性路径规划(设计文档 §6 adaptive_routing)。

基于已有产物与复杂度决策各阶段 run/skip。确定性决策由 FSM 兜底:
汇合点(6 / 9)永不可跳过,skip 只是建议。
"""
from __future__ import annotations

from typing import Dict, Optional

ALL_STAGES = ["0", "1", "2", "3", "4", "5A", "5B", "6", "7", "8", "9", "10"]
# 汇合点:前置多支线,永不可 skip
JOIN_STAGES = {"6", "9"}


def plan(inputs: Optional[dict] = None) -> dict:
    """inputs: {has_contract, has_tech_plan, has_branch, complexity}。

    返回 {stages: {stage: run|skip}, fast_path: bool, skipped: [...]}。
    """
    inputs = inputs or {}
    decisions: Dict[str, str] = {s: "run" for s in ALL_STAGES}

    # 已有契约 → 跳过需求分析(1)与契约设计(2)
    if inputs.get("has_contract"):
        decisions["1"] = "skip"
        decisions["2"] = "skip"
    # 已有技术方案 → 跳过 Stage 3
    if inputs.get("has_tech_plan"):
        decisions["3"] = "skip"
    # 已有分支 → 跳过 Stage 4
    if inputs.get("has_branch"):
        decisions["4"] = "skip"

    # 汇合点永不可跳过(即使被误标记,FSM 也会兜底)
    for s in JOIN_STAGES:
        decisions[s] = "run"

    fast_path = inputs.get("complexity") == "L"
    skipped = [s for s in ALL_STAGES if decisions[s] == "skip"]

    return {"stages": decisions, "fast_path": fast_path, "skipped": skipped}


def main(argv=None) -> int:
    import argparse
    import json

    p = argparse.ArgumentParser(description="确定性路径规划")
    p.add_argument("--has-contract", action="store_true")
    p.add_argument("--has-tech-plan", action="store_true")
    p.add_argument("--has-branch", action="store_true")
    p.add_argument("--complexity", choices=["L", "M", "H"])
    args = p.parse_args(argv)

    inputs = {
        "has_contract": args.has_contract,
        "has_tech_plan": args.has_tech_plan,
        "has_branch": args.has_branch,
        "complexity": args.complexity,
    }
    print(json.dumps(plan(inputs), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
