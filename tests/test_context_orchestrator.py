#!/usr/bin/env python3
"""上下文编排自测。运行:python3 tests/test_context_orchestrator.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.context_orchestrator import budget_context, build_dispatch_context, orchestrate, select_sections  # noqa: E402


def test_select_sections():
    # 需求分析注入业务/QA 知识；实现阶段按端注入；评审仍保留工程规范。
    assert "business-knowledge" in select_sections("1")
    assert "qa-knowledge" in select_sections("1")
    assert "architecture" not in select_sections("1")
    assert "backend-knowledge" in select_sections("5A")
    assert "frontend-knowledge" not in select_sections("5A")
    assert "frontend-knowledge" in select_sections("5B")
    assert "conventions" in select_sections("7")
    assert "architecture" in select_sections("3")


def test_budget_context():
    sections = [
        {"name": "a", "text": "x" * 100, "priority": 0},
        {"name": "b", "text": "y" * 100, "priority": 1},
        {"name": "c", "text": "z" * 100, "priority": 2},
    ]
    # 预算只够 a+b(每个约 50 token)
    kept = budget_context(sections, max_tokens=101)
    assert [s["name"] for s in kept] == ["a", "b"], kept


def test_orchestrate():
    sections = {
        "agenda": "AG", "business-knowledge": "BUS", "qa-knowledge": "QA",
        "domain-model": "DM", "architecture": "ARCH",
    }
    out = orchestrate("1", sections)
    assert "AG" in out and "BUS" in out and "QA" in out and "DM" in out and "ARCH" not in out


def test_build_dispatch_context_filters_entities_and_repo_sections():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        docs = repo / ".agents" / "docs"
        docs.mkdir(parents=True)
        (docs / "architecture.md").write_text("ARCH", encoding="utf-8")
        (docs / "conventions.md").write_text("CONV", encoding="utf-8")
        (docs / "domain-model.md").write_text("MODEL", encoding="utf-8")
        context = build_dispatch_context("2", "api.yaml", ["Order"], repo, max_tokens=4000)
        names = [section["name"] for section in context["sections"]]
        assert context["schema"] == "dispatch-context/v1"
        assert "business-knowledge" in names and "backend-knowledge" in names and "frontend-knowledge" in names
        assert "Order" in context["text"] and "architecture" not in names
        assert "CONV" in context["text"] and "MODEL" in context["text"]
        assert context["estimated_tokens"] <= 4000


def test_build_dispatch_context_respects_budget():
    context = build_dispatch_context("1", "api.yaml", ["Order"], max_tokens=10)
    assert context["estimated_tokens"] <= 10
    assert context["omitted_sections"], context


def main():
    test_select_sections()
    test_budget_context()
    test_orchestrate()
    test_build_dispatch_context_filters_entities_and_repo_sections()
    test_build_dispatch_context_respects_budget()
    print("OK: context_orchestrator 自测通过(5 组断言)")


if __name__ == "__main__":
    main()
