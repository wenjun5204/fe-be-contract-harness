#!/usr/bin/env python3
"""结构化需求 Spec 协议 + 确定性守卫(SDD 核心,参考 super-assistant requirements-confirmation)。

把需求分析从「自然语言 markdown PRD」升级为「可机器校验的结构化 Spec」:
- 澄清有界(≤3 轮,每轮 3-5 问)
- 类别覆盖(11 类,高影响类必须覆盖)
- 事实有来源(provenance)
- 质量门(占位 / 歧义 / 契约就绪性)
- 契约就绪性(数据实体有字段类型/边界,错误码已定义 → 可直接派生 OpenAPI)

这是 Stage 1 → Stage 2 的确定性门控(由 workflow_fsm 调用)。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

MAX_CLARIFICATION_ROUNDS = 3
MIN_QUESTIONS_PER_ROUND = 3
MAX_QUESTIONS_PER_ROUND = 5

# 11 个问题类别;HIGH_IMPACT 必须覆盖(否则阻断进入契约设计)
QUESTION_CATEGORIES = (
    "goal_value",         # 目标与价值
    "users_permissions",  # 用户与权限
    "scope",              # 范围
    "main_flow",          # 主流程
    "state",              # 状态
    "data",               # 数据/字段(契约核心)
    "exceptions",         # 异常/错误码(契约核心)
    "interaction",        # 交互
    "dependencies",       # 依赖
    "non_functional",     # 非功能
    "acceptance",         # 验收
)

HIGH_IMPACT = frozenset({
    "goal_value", "users_permissions", "scope", "main_flow",
    "state", "data", "exceptions", "dependencies", "acceptance",
})

# 事实来源优先级(高 → 低);低优先级来源不能覆盖已确认事实
SOURCE_PRIORITY = ("user", "user_document", "code", "ai_inference")

_PLACEHOLDER_RE = re.compile(r"\b(?:TBD|TODO|TO\s*DO)\b|待定|后续再定", re.IGNORECASE)
_AMBIGUOUS_RE = re.compile(r"适当处理|必要时|按需|视情况|尽量|合理处理")


def default_requirements_spec() -> Dict[str, Any]:
    """返回一份新的结构化需求 Spec 协议(JSON 可序列化)。"""
    return {
        "schema_version": "1.0",
        "status": "scope_assessment",  # scope_assessment -> clarification -> ready -> approved
        "scope": {
            "complexity": None,        # L / M / H
            "subsystems": [],
            "cross_team_dependencies": [],
            "split_required": False,
            "split_decision": None,    # None | coupled | split | defer
        },
        "clarification": {
            "round": 0,
            "max_rounds": MAX_CLARIFICATION_ROUNDS,
            "questions": [],
            "answers": [],
            "confirmed_facts": [],   # [{fact, source}]
            "assumptions": [],       # [{assumption, accepted}]
            "unresolved_questions": [],  # [{question, category}]
            "coverage": {cat: "pending" for cat in QUESTION_CATEGORIES},
        },
        "contract_readiness": {
            "entities": [],          # [{name, fields: [{name, type, required, bounds}], states: []}]
            "error_codes": [],       # [{code, meaning}]
        },
        "document": {
            "approved": False,
            "quality_gate": "pending",  # pending | passed | failed
        },
    }


def set_scope(spec: dict, complexity: str, subsystems: List[str] = None,
              cross_team_dependencies: List[str] = None) -> dict:
    spec["scope"]["complexity"] = complexity
    spec["scope"]["subsystems"] = subsystems or []
    spec["scope"]["cross_team_dependencies"] = cross_team_dependencies or []
    return spec


def record_clarification_questions(spec: dict, questions: List[dict]) -> dict:
    """questions: [{question, category}]。有界校验:每轮 3-5 问,≤3 轮。"""
    cl = spec["clarification"]
    if len(questions) < MIN_QUESTIONS_PER_ROUND or len(questions) > MAX_QUESTIONS_PER_ROUND:
        raise ValueError(f"每轮问题数须在 {MIN_QUESTIONS_PER_ROUND}~{MAX_QUESTIONS_PER_ROUND} 之间,得到 {len(questions)}")
    if cl["round"] >= cl["max_rounds"]:
        raise ValueError(f"澄清轮次已达上限 {cl['max_rounds']}")
    cl["round"] += 1
    cl["questions"].extend(questions)
    return spec


def record_answers(spec: dict, answers: List[dict]) -> dict:
    """answers: [{question, answer}]。回答即视为事实确认(需带来源,默认 user)。"""
    cl = spec["clarification"]
    for a in answers:
        cl["answers"].append(a)
        cl["confirmed_facts"].append({"fact": a.get("answer"), "source": a.get("source", "user")})
        cat = a.get("category")
        if cat in cl["coverage"]:
            cl["coverage"][cat] = "covered"
    return spec


def set_contract_readiness(spec: dict, entities: List[dict], error_codes: List[dict]) -> dict:
    """entities: [{name, fields: [{name, type, required, bounds}], states: []}]"""
    spec["contract_readiness"]["entities"] = entities
    spec["contract_readiness"]["error_codes"] = error_codes
    return spec


def coverage_gaps(spec: dict) -> List[str]:
    """返回未覆盖的高影响类别。"""
    cov = spec["clarification"]["coverage"]
    return [c for c in HIGH_IMPACT if cov.get(c) != "covered"]


def scan_spec_quality(text: str) -> List[dict]:
    """质量门:占位符 / 歧义词 / 契约就绪性。返回 [{check, level, hint}]。"""
    issues = []
    for m in _PLACEHOLDER_RE.finditer(text):
        issues.append({"check": "placeholder", "level": "P1", "hint": f"含占位符: {m.group(0)}"})
    for m in _AMBIGUOUS_RE.finditer(text):
        issues.append({"check": "ambiguity", "level": "P1", "hint": f"含歧义词: {m.group(0)}"})
    return issues


def mark_quality_gate(spec: dict, passed: bool) -> dict:
    spec["document"]["quality_gate"] = "passed" if passed else "failed"
    return spec


def approve(spec: dict) -> dict:
    spec["document"]["approved"] = True
    spec["status"] = "approved"
    return spec


def validate_requirements_completion(state_data: dict) -> List[str]:
    """Stage 1 进入 Stage 2 前的确定性门控。返回缺失/不满足项列表(空 = 通过)。"""
    spec = state_data.get("requirements_spec")
    if not spec:
        return ["requirements_spec 缺失(未产出结构化需求 Spec)"]
    if not isinstance(spec, dict):
        return [
            "requirements_spec 必须是内嵌的结构化 Spec 对象(完整 JSON),"
            "不能是文件路径字符串——完整对象随 outputs 落盘 state,才能被 FSM 机验"
        ]

    errors: List[str] = []
    if not spec.get("scope", {}).get("complexity"):
        errors.append("复杂度评估未完成")
    gaps = coverage_gaps(spec)
    if gaps:
        errors.append(f"需求覆盖不完整(高影响类未覆盖): {', '.join(sorted(gaps))}")
    if spec["clarification"].get("unresolved_questions"):
        errors.append("存在未解决的高影响问题")
    if spec.get("document", {}).get("quality_gate") != "passed":
        errors.append("需求文档质量门未通过(占位/歧义/契约就绪性)")
    if not spec.get("document", {}).get("approved"):
        errors.append("需求 Spec 未确认(approved)")
    # 契约就绪性:能派生 OpenAPI 的最小前提
    entities = spec.get("contract_readiness", {}).get("entities", [])
    if not entities:
        errors.append("契约就绪性不足:未定义数据实体(无法派生 OpenAPI schemas)")
    else:
        for e in entities:
            if not e.get("fields"):
                errors.append(f"实体 {e.get('name', '?')} 未定义字段(无法派生 schema)")
                break
    if not spec.get("contract_readiness", {}).get("error_codes"):
        errors.append("契约就绪性不足:未定义错误码(无法派生错误响应)")
    return errors


def main(argv=None) -> int:
    import argparse
    import pathlib

    p = argparse.ArgumentParser(description="结构化需求 Spec 校验")
    p.add_argument("spec_file")
    args = p.parse_args(argv)

    spec = json.loads(pathlib.Path(args.spec_file).read_text(encoding="utf-8"))
    errors = validate_requirements_completion({"requirements_spec": spec})
    print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
