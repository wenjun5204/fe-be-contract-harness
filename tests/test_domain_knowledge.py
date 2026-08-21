#!/usr/bin/env python3
"""领域知识库自测。运行:python3 tests/test_domain_knowledge.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.domain_knowledge import identify_gaps, list_domains, search, seed  # noqa: E402


def test_domains():
    ds = list_domains()
    assert set(ds) >= {"business", "frontend", "backend", "qa"}, ds


def test_search_sample():
    hits = search("订单", "business")
    assert hits, "应在示例知识中检索到「订单」"


def test_seed_and_gaps():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        seed("business", "order", "Order 订单 amount 金额", root)
        spec = {"contract_readiness": {"entities": [
            {"name": "Order", "fields": [{"name": "amount"}]},
            {"name": "Payment", "fields": [{"name": "channel"}]},
        ]}}
        gaps = identify_gaps(spec, "business", root)
        assert "Order" not in gaps and "amount" not in gaps  # 已覆盖
        assert "Payment" in gaps and "channel" in gaps  # 未覆盖 → 模糊点


def main():
    test_domains()
    test_search_sample()
    test_seed_and_gaps()
    print("OK: domain_knowledge 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
