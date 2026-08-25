#!/usr/bin/env python3
"""领域知识库自测。运行:python3 tests/test_domain_knowledge.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.domain_knowledge import (  # noqa: E402
    coverage_report,
    find_conflicts,
    identify_gaps,
    list_domains,
    search,
    seed,
    validate_entry,
    write_entry,
)


def _entry(entry_id="order-core", fields=None, error_codes=None, status="confirmed", source="user"):
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
        "content": "订单金额按分存储；重复提交返回原订单。",
    }


def test_domains():
    assert set(list_domains()) >= {"business", "frontend", "backend", "qa"}


def test_search_sample():
    hits = search("订单", "business")
    assert hits, "应在示例知识中检索到「订单」"
    assert hits[0]["status"] == "confirmed"


def test_safe_write_and_schema_validation():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        entry = _entry()
        path = write_entry(entry, root)
        assert path.exists()
        assert '"status": "confirmed"' in path.read_text(encoding="utf-8")
        try:
            write_entry(entry, root)
            assert False, "默认 create 不得覆盖同名条目"
        except FileExistsError:
            pass
        assert validate_entry(_entry(status="confirmed", source="ai_inference"))
        assert not validate_entry(_entry(status="assumption", source="ai_inference"))


def test_precise_coverage_and_conflicts():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_entry(_entry(), root)
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
        assert find_conflicts(conflict, root)[0]["kind"] == "field"
        try:
            write_entry(conflict, root)
            assert False, "确认知识冲突不得静默写入"
        except ValueError as exc:
            assert "冲突" in str(exc)


def test_legacy_entry_does_not_prove_structured_coverage():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        legacy = root / "business" / "old.md"
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


def main():
    test_domains()
    test_search_sample()
    test_safe_write_and_schema_validation()
    test_precise_coverage_and_conflicts()
    test_legacy_entry_does_not_prove_structured_coverage()
    test_seed_compatibility()
    print("OK: domain_knowledge 自测通过(6 组断言)")


if __name__ == "__main__":
    main()
