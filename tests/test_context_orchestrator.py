#!/usr/bin/env python3
"""上下文编排自测。运行:python3 tests/test_context_orchestrator.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.context_orchestrator import (  # noqa: E402
    budget_context,
    build_dispatch_context,
    estimate_tokens,
    orchestrate,
    select_sections,
)


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
    # 预算只够 a+b(ASCII 每字符 1/4 token,每个约 25 token → 101 预算实际全放下;
    # 用紧预算验证取舍)
    kept = budget_context(sections, max_tokens=51)
    assert [s["name"] for s in kept] == ["a", "b"], kept


def test_estimate_tokens_cjk():
    """P0-7: ASCII ~1/4 token,CJK ~1 token;中文预算不再被低估一倍。"""
    assert estimate_tokens("x" * 100) == 25  # 纯 ASCII:4 字符/token
    assert estimate_tokens("订单" * 100) == 200  # 纯 CJK:每字 1 token
    mixed = estimate_tokens("订单" * 50 + "x" * 100)  # 100 CJK + 100 ASCII
    assert mixed == 100 + 25, mixed
    assert estimate_tokens("") == 1  # 下限


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
