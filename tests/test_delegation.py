#!/usr/bin/env python3
"""委派协议自测。运行:python3 tests/test_delegation.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.delegation import issue_receipt, load_policy, validate_dispatch, validate_receipt  # noqa: E402


def test_receipt():
    r = issue_receipt("2", "contract/contract-designer", "tok-1")
    assert validate_receipt(r, "2")
    assert not validate_receipt(r, "3")  # 阶段不匹配
    assert not validate_receipt(None, "2")


def test_valid_dispatch():
    policy = load_policy()
    r = issue_receipt("2", "contract/contract-designer", "tok-1")
    res = validate_dispatch("2", r, {"openapi_contract": "api.yaml"}, policy)
    assert res["ok"], res


def test_fail_closed():
    policy = load_policy()
    # 1. 无 receipt
    res = validate_dispatch("2", None, {"openapi_contract": "api.yaml"}, policy)
    assert not res["ok"]
    # 2. subagent 不匹配
    r = issue_receipt("2", "wrong/agent", "tok")
    res = validate_dispatch("2", r, {"openapi_contract": "api.yaml"}, policy)
    assert not res["ok"]
    # 3. 产出缺失
    r = issue_receipt("2", "contract/contract-designer", "tok")
    res = validate_dispatch("2", r, {}, policy)
    assert not res["ok"] and "openapi_contract" in " ".join(res["reasons"])


def main():
    test_receipt()
    test_valid_dispatch()
    test_fail_closed()
    print("OK: delegation 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
