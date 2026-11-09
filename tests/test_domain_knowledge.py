#!/usr/bin/env python3
"""领域知识库自测。运行:python3 tests/test_domain_knowledge.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.domain_knowledge import (  # noqa: E402
    confirm_entry,
    coverage_report,
    find_conflicts,
    find_orphans,
    identify_gaps,
    list_domains,
    list_products,
    load_entries,
    search,
    seed,
    validate_entry,
    write_entry,
)


def _entry(entry_id="order-core", fields=None, error_codes=None, status="confirmed", source="user",
           content="订单金额按分存储；重复提交返回原订单。"):
    return {
        "id": entry_id,
        "domain": "business",
        "entity": "Order",
        "type": "lifecycle",
        "status": status,
        "source": source,
        "fields": fields if fields is not None else [{"name": "amount", "type": "integer"}],
        "states": ["PENDING", "PAID"],
        "error_codes": error_codes if error_codes is not None else [{"code": 409, "meaning": "duplicate"}],
        "content": content,
    }


def test_domains():
    assert set(list_domains()) >= {"business", "frontend", "backend", "qa"}


def test_search_sample():
    hits = search("订单", "business")
    assert hits, "应在示例知识中检索到「订单」"
    assert hits[0]["status"] == "confirmed"
    assert hits[0]["scope"] == "global"


def test_safe_write_and_schema_validation():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        entry = _entry()
        path = write_entry(entry, root, scope="global")
        assert path.exists()
        assert path.parent == root / "_global" / "business"
        assert '"status": "confirmed"' in path.read_text(encoding="utf-8")
        try:
            write_entry(entry, root, scope="global")
            assert False, "默认 create 不得覆盖同名条目"
        except FileExistsError:
            pass
        assert validate_entry(_entry(status="confirmed", source="ai_inference"))
        assert not validate_entry(_entry(status="assumption", source="ai_inference"))


def test_scope_isolation():
    """方案 B 核心:目录即作用域——产品知识不进其他产品的读侧;
    写侧无 product 默认 pending(fail-closed,绝不落 _global/)。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # 全局约定 + 两个产品各自的私有知识
        write_entry(_entry(entry_id="global-order"), root, scope="global")
        write_entry(_entry(entry_id="alpha-rule", content="Alpha 产品的私有规则"), root, product="alpha")
        write_entry(_entry(entry_id="beta-rule", content="Beta 产品的私有规则"), root, product="beta")

        # alpha 读侧:全局 ∪ alpha,看不到 beta
        ids = {e["id"] for e in load_entries("business", root, product="alpha")}
        assert ids == {"global-order", "alpha-rule"}, ids
        # 无 product(冷启动未解析):仅全局
        assert {e["id"] for e in load_entries("business", root)} == {"global-order"}
        # scope 标记随条目携带
        scopes = {e["id"]: e["scope"] for e in load_entries("business", root, product="alpha")}
        assert scopes == {"global-order": "global", "alpha-rule": "product"}

        # 写侧 fail-closed:无 product 无 scope → pending/,不落 _global/
        pending_path = write_entry(_entry(entry_id="orphan-drift", status="assumption", source="ai_inference"), root)
        assert pending_path.parent == root / "pending" / "business", pending_path
        # pending 不进读侧(悬置待归位,不是可注入知识)
        assert "orphan-drift" not in {e["id"] for e in load_entries("business", root, product="alpha")}

        # 非法 product 目录名拒绝(目录名即接口边界)
        try:
            write_entry(_entry(entry_id="bad"), root, product="../evil")
            assert False, "非法 product 应拒绝"
        except ValueError:
            pass

        # 孤儿检测
        assert list_products(root) == ["alpha", "beta"]
        assert find_orphans(root, known=["alpha"]) == ["beta"]
        assert find_orphans(root, known=["alpha", "beta"]) == []


def test_confirm_entry_flow():
    """E3 知识确认流转:assumption → confirmed 带审计字段;fail-closed 拒误改。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # AI 推断落 assumption(E2 回流归位到产品作用域的形态)
        write_entry(_entry(entry_id="draft-rule", status="assumption", source="ai_inference"), root, product="alpha")
        # confirm 成功:审计字段落盘,升级后可被该产品 confirmed 层检索
        res = confirm_entry("business", "draft-rule", "liuwenjun", root, product="alpha")
        assert res["ok"] and res["confirmed_by"] == "liuwenjun", res
        path = Path(res["file"])
        assert path.parent == root / "products" / "alpha" / "business"
        text = path.read_text(encoding="utf-8")
        assert '"status": "confirmed"' in text and "liuwenjun" in text, text
        entries = [e for e in load_entries("business", root, product="alpha") if e["id"] == "draft-rule"]
        assert entries and entries[0]["status"] == "confirmed", entries

        # fail-closed:已 confirmed 不可重复确认
        try:
            confirm_entry("business", "draft-rule", "someone", root, product="alpha")
            assert False, "重复 confirm 应拒绝"
        except ValueError as e:
            assert "已是 confirmed" in str(e), e
        # deprecated 不可直接 confirm
        write_entry(_entry(entry_id="dead-rule", status="deprecated", source="user"), root, product="alpha")
        try:
            confirm_entry("business", "dead-rule", "someone", root, product="alpha")
            assert False, "deprecated confirm 应拒绝"
        except ValueError as e:
            assert "deprecated" in str(e), e
        # 不存在 → FileNotFoundError
        try:
            confirm_entry("business", "no-such", "x", root)
            assert False, "不存在条目应报错"
        except FileNotFoundError:
            pass


def test_confirm_to_global_is_explicit_human_decision():
    """跨产品通用化 = 人工显式决策(confirm to_global);自动写侧永远到不了 _global/。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_entry(_entry(entry_id="alpha-only", status="assumption", source="ai_inference"), root, product="alpha")
        res = confirm_entry("business", "alpha-only", "liuwenjun", root, product="alpha", to_global=True)
        assert res["scope"] == "global", res
        # 旧位置移除(目录即作用域,不留双份);全局层可检索
        assert not (root / "products" / "alpha" / "business" / "alpha-only.md").exists()
        assert {e["id"] for e in load_entries("business", root)} == {"alpha-only"}
        # beta 也看得到(已升级为跨产品通用知识)
        assert {e["id"] for e in load_entries("business", root, product="beta")} == {"alpha-only"}


def test_precise_coverage_and_conflicts():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_entry(_entry(), root, scope="global")
        spec = {"contract_readiness": {"entities": [
            {"name": "Order", "fields": [{"name": "amount"}, {"name": "status"}], "states": ["PENDING", "CANCELLED"]},
            {"name": "Payment", "fields": [{"name": "channel"}], "states": []},
        ], "error_codes": [{"code": 409, "meaning": "duplicate"}, {"code": 422, "meaning": "invalid state"}]}}
        report = coverage_report(spec, "business", root)
        assert report["missing_entity"] == ["Payment"], report
        assert {item["field"] for item in report["missing_field_definition"]} == {"status", "channel"}, report
        assert report["missing_state_definition"] == [{"entity": "Order", "state": "CANCELLED"}], report
        assert report["missing_error_mapping"] == [{"code": 422, "meaning": "invalid state"}], report
        assert set(identify_gaps(spec, "business", root)) == {"Payment", "status", "channel"}

        conflict = _entry("order-other", fields=[{"name": "amount", "type": "string"}])
        assert find_conflicts(conflict, root, scope="global")[0]["kind"] == "field"
        try:
            write_entry(conflict, root, scope="global")
            assert False, "确认知识冲突不得静默写入"
        except ValueError as exc:
            assert "冲突" in str(exc)


def test_legacy_entry_does_not_prove_structured_coverage():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        legacy = root / "_global" / "business" / "old.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("Order 的 amount 字段需要展示", encoding="utf-8")
        spec = {"contract_readiness": {"entities": [{"name": "Order", "fields": [{"name": "amount"}]}]}}
        report = coverage_report(spec, "business", root)
        assert report["missing_entity"] == ["Order"]
        assert report["missing_field_definition"] == [{"entity": "Order", "field": "amount"}]
        assert report["legacy_entries"] == ["old"]


def test_seed_compatibility():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        path = seed("business", "payment-rule", "Payment channel 必须明确", root)
        assert path.exists()
        assert path.parent == root / "_global" / "business"


def main():
    test_domains()
    test_search_sample()
    test_safe_write_and_schema_validation()
    test_scope_isolation()
    test_confirm_entry_flow()
    test_confirm_to_global_is_explicit_human_decision()
    test_precise_coverage_and_conflicts()
    test_legacy_entry_does_not_prove_structured_coverage()
    test_seed_compatibility()
    print("OK: domain_knowledge 自测通过(9 组断言)")


if __name__ == "__main__":
    main()
