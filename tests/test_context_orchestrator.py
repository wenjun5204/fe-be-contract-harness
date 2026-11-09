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


def test_kb_scope_isolation_and_exact_entity_match():
    """方案 B 回归(两根因的验收):
    - 根因 #1(convention 恒注入泄漏):产品私有知识不再进入其他产品的 context;
    - 根因 #3(子串匹配误报):OrderReturn 不再命中 entity Order;
    - 产品自己的知识(convention 型业务规则包)在自己的 run 中照常注入。
    """
    import contextlib

    import lib.domain_knowledge as dk

    @contextlib.contextmanager
    def _kb(tmpdir):
        backup = dk.KB_DIR
        dk.KB_DIR = Path(tmpdir) / "kb"
        try:
            yield
        finally:
            dk.KB_DIR = backup

    with tempfile.TemporaryDirectory() as d:
        with _kb(d):
            # _global:跨项目约定 + 可复用订单域知识;products/fe-backend-mini:全家福
            dk.write_entry({
                "id": "global-conventions", "domain": "backend", "entity": "ApiConvention",
                "type": "convention", "status": "confirmed", "source": "user",
                "fields": [], "states": [], "error_codes": [],
                "content": "统一错误码规范:400 参数错误。",
            }, scope="global")
            dk.write_entry({
                "id": "order-core", "domain": "business", "entity": "Order",
                "type": "lifecycle", "status": "confirmed", "source": "user",
                "fields": [{"name": "amount", "type": "integer"}], "states": [], "error_codes": [],
                "content": "订单金额按分存储。",
            }, scope="global")
            dk.write_entry({
                "id": "family-blessing-v15", "domain": "business", "entity": "FamilyBlessing",
                "type": "convention", "status": "confirmed", "source": "user",
                "fields": [], "states": [], "error_codes": [],
                "content": "福值只涨不跌,所有变更走 BlessEvent 事件路径。",
            }, product="fe-backend-mini")

            # ① stripe run(有 Order 实体):全局注入、order.md 命中、全家福不可见
            # (stage 2 同时覆盖 business/backend 知识段,验证两层注入口径一致)
            ctx = build_dispatch_context("2", "stripe.json", ["Order", "Charge"], product="stripe")
            assert "订单金额按分存储" in ctx["text"], ctx["text"]
            assert "统一错误码规范" in ctx["text"]
            assert "福值" not in ctx["text"] and "FamilyBlessing" not in ctx["text"], "跨产品泄漏!"
            assert ctx["product"] == "stripe"

            # ② yivote run(无 Order 实体):business 为空——不能拿别人的知识凑数
            ctx2 = build_dispatch_context("1", "yivote.json", ["Vote"], product="yivote")
            names2 = [s["name"] for s in ctx2["sections"]]
            assert "business-knowledge" not in names2, names2

            # ③ 子串误报修复:OrderReturn ≠ Order
            ctx3 = build_dispatch_context("1", "stripe.json", ["OrderReturn"], product="stripe")
            assert "business-knowledge" not in [s["name"] for s in ctx3["sections"]], "子串误报回归!"

            # ④ 全家福自己的 run:照常注入(隔离不是没收)
            ctx4 = build_dispatch_context("1", "mini.json", ["FamilyBlessing"], product="fe-backend-mini")
            assert "福值只涨不跌" in ctx4["text"], ctx4["text"]

            # ⑤ 冷启动(product=None):仅全局层
            ctx5 = build_dispatch_context("1", "cold.json", ["Order"])
            assert "订单金额按分存储" in ctx5["text"] and "福值" not in ctx5["text"]


def main():
    test_select_sections()
    test_budget_context()
    test_orchestrate()
    test_build_dispatch_context_filters_entities_and_repo_sections()
    test_build_dispatch_context_respects_budget()
    test_kb_scope_isolation_and_exact_entity_match()
    print("OK: context_orchestrator 自测通过(6 组断言)")


if __name__ == "__main__":
    main()
