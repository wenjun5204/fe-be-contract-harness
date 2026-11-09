#!/usr/bin/env python3
"""product_scope 自测:product_id 三级解析链(方案 B §3.3)。
运行:python3 tests/test_product_scope.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.product_scope import resolve_product_id, slugify  # noqa: E402


def test_slugify():
    assert slugify("咦投票 API") == "api"
    assert slugify("Petstore Service") == "petstore-service"
    assert slugify("  Fe--Backend__MINI! ") == "fe-backend-mini"
    assert slugify(" Stripe / Payments (v2) ") == "stripe-payments-v2"
    assert slugify("") == ""
    assert slugify("---") == ""
    long_name = "a" * 100
    assert len(slugify(long_name)) == 64


def test_resolution_chain():
    model = {"info": {"title": "咦投票 API", "version": "1"}}
    # 1. 显式 --product 最高优先(覆盖 state 与 title)
    pid, src = resolve_product_id("yivote", model, {"product_id": "pinned"})
    assert (pid, src) == ("yivote", "explicit")
    # 2. state 固化 > title 派生(重跑沿用;同产品改 title 不换 scope)
    pid, src = resolve_product_id(None, {"info": {"title": "New Title"}}, {"product_id": "pinned"})
    assert (pid, src) == ("pinned", "state")
    # 3. title 派生(零配置冷启动)
    pid, src = resolve_product_id(None, model, {})
    assert (pid, src) == ("api", "title")
    # 4. 全部解析不出 → None(读侧仅全局;写侧 pending 兜底)
    pid, src = resolve_product_id(None, {"info": {}}, {})
    assert (pid, src) == (None, "unresolved")
    pid, src = resolve_product_id(None, None, None)
    assert (pid, src) == (None, "unresolved")
    # 5. 非法显式名(slug 化后为空)不炸,降级后续链路
    pid, src = resolve_product_id("///", {"info": {"title": "Petstore"}}, {})
    assert (pid, src) == ("petstore", "title")


def main():
    test_slugify()
    test_resolution_chain()
    print("OK: product_scope 自测通过(2 组断言)")


if __name__ == "__main__":
    main()
