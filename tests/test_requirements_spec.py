#!/usr/bin/env python3
"""结构化需求 Spec 自测。运行:python3 tests/test_requirements_spec.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.requirements_spec import (  # noqa: E402
    approve,
    coverage_gaps,
    default_requirements_spec,
    mark_quality_gate,
    record_answers,
    record_clarification_questions,
    scan_spec_quality,
    set_contract_readiness,
    set_scope,
    validate_requirements_completion,
)

HIGH = ["goal_value", "users_permissions", "scope", "main_flow", "state",
        "data", "exceptions", "dependencies", "acceptance"]


def _complete_spec():
    spec = default_requirements_spec()
    set_scope(spec, "M", ["fe", "be"])
    questions = [{"question": f"q-{c}", "category": c} for c in HIGH[:5]]
    record_clarification_questions(spec, questions)
    answers = [{"question": q["question"], "answer": f"a-{q['category']}", "category": q["category"]} for q in questions]
    record_answers(spec, answers)
    for c in HIGH[5:]:
        spec["clarification"]["coverage"][c] = "covered"
    set_contract_readiness(
        spec,
        [{"name": "Pet", "fields": [{"name": "id", "type": "integer", "required": True, "bounds": None}]}],
        [{"code": "404", "meaning": "not found"}],
    )
    mark_quality_gate(spec, True)
    approve(spec)
    return spec


def test_default_and_gaps():
    spec = default_requirements_spec()
    assert coverage_gaps(spec)  # 全 pending → 有 gap
    assert validate_requirements_completion({"requirements_spec": spec})  # 未完成 → 有错误


def test_bounded_clarification():
    spec = default_requirements_spec()
    try:
        record_clarification_questions(spec, [{"question": "x", "category": "goal_value"}])  # 1 个 → 越界
        assert False, "应抛 ValueError"
    except ValueError:
        pass


def test_complete_spec_passes():
    spec = _complete_spec()
    assert coverage_gaps(spec) == []
    assert validate_requirements_completion({"requirements_spec": spec}) == []


def test_quality_scan():
    issues = scan_spec_quality("待定, 按需处理")
    assert any(i["check"] == "placeholder" for i in issues)
    assert any(i["check"] == "ambiguity" for i in issues)


def main():
    test_default_and_gaps()
    test_bounded_clarification()
    test_complete_spec_passes()
    test_quality_scan()
    print("OK: requirements_spec 自测通过(4 组断言)")


if __name__ == "__main__":
    main()
