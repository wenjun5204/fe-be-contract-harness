#!/usr/bin/env python3
"""委派协议自测。运行:python3 tests/test_delegation.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.delegation import (  # noqa: E402
    allowed_subagents,
    consume_receipt,
    issue_receipt,
    load_policy,
    register_receipt,
    resolve_subagents,
    receipt_subagents,
    validate_dispatch,
    validate_receipt,
    validate_receipt_registered,
)
from lib.state_manager import init_state  # noqa: E402


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


def test_dynamic_codegen_subagents():
    """5A/5B 必须基于实际技术栈解析并校验 Agent，支持多栈 receipt。"""
    policy = load_policy()
    assert resolve_subagents("5A", ["java"], policy) == ["codegen/java-codegen"]
    assert resolve_subagents("5B", ["vue"], policy) == ["codegen/vue-codegen"]
    assert resolve_subagents("5A", ["node", "java"], policy) == [
        "codegen/node-codegen", "codegen/java-codegen",
    ]
    assert resolve_subagents("5B", policy=policy, for_skip=True) == ["codegen/react-codegen"]

    assert set(allowed_subagents("5A", policy)) == {"codegen/node-codegen", "codegen/java-codegen"}
    assert set(allowed_subagents("5B", policy)) == {"codegen/react-codegen", "codegen/vue-codegen"}
    assert allowed_subagents("2", policy) == ["contract/contract-designer"]

    receipt = issue_receipt("5A", ["codegen/node-codegen", "codegen/java-codegen"], "tok-multi")
    assert receipt_subagents(receipt) == ["codegen/node-codegen", "codegen/java-codegen"]
    res = validate_dispatch("5A", receipt, {"changed_files": ["x"], "coverage": "ok"}, policy)
    assert res["ok"], res

    invalid = issue_receipt("5A", "codegen/react-codegen", "tok-wrong")
    res = validate_dispatch("5A", invalid, {"changed_files": ["x"], "coverage": "ok"}, policy)
    assert not res["ok"] and "subagent 不匹配" in " ".join(res["reasons"]), res


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


def test_registered_gate():
    """带 state_file 时:未登记 / token 伪造 / 已消费 均拒绝;登记且未使用才放行。"""
    policy = load_policy()
    with tempfile.TemporaryDirectory() as d:
        sf = Path(d) / "state.json"
        init_state(sf, "deleg")
        outputs = {"openapi_contract": "api.yaml"}
        # 1. 未登记 → 拒绝
        r = issue_receipt("2", "contract/contract-designer", "tok-2")
        res = validate_dispatch("2", r, outputs, policy, state_file=sf)
        assert not res["ok"] and "未登记" in " ".join(res["reasons"]), res
        # 2. 登记后 → 放行
        register_receipt(sf, r)
        res = validate_dispatch("2", r, outputs, policy, state_file=sf)
        assert res["ok"], res
        # 3. token 伪造 → 拒绝
        fake = issue_receipt("2", "contract/contract-designer", "attacker")
        res = validate_dispatch("2", fake, outputs, policy, state_file=sf)
        assert not res["ok"] and "token 与登记不符" in " ".join(res["reasons"]), res
        # 4. 消费后重放 → 拒绝
        consume_receipt(sf, "2")
        res = validate_dispatch("2", r, outputs, policy, state_file=sf)
        assert not res["ok"] and "已被消费" in " ".join(res["reasons"]), res


def test_validate_registered_pure():
    """validate_receipt_registered 纯函数语义。"""
    state = {"receipts": {}}
    r = issue_receipt("2", "contract/contract-designer", "tok")
    assert validate_receipt_registered(state, "2", r) is not None  # 未登记
    state["receipts"]["2"] = {"receipt": r, "used": False}
    assert validate_receipt_registered(state, "2", r) is None  # 通过
    assert validate_receipt_registered(state, "2", None) is not None  # 无 receipt
    state["receipts"]["2"]["used"] = True
    assert validate_receipt_registered(state, "2", r) is not None  # 已消费


def main():
    test_receipt()
    test_valid_dispatch()
    test_dynamic_codegen_subagents()
    test_fail_closed()
    test_registered_gate()
    test_validate_registered_pure()
    print("OK: delegation 自测通过(6 组断言)")


if __name__ == "__main__":
    main()


def test_register_rejects_wrong_stage_subagent():
    """register 入口即校验 subagent 匹配:错误阶段的 Agent 在登记时被拒(带纠错提示),
    而不是等 complete 时(整段工作做完后)才拒绝。"""
    with tempfile.TemporaryDirectory() as d:
        sf = Path(d) / "state.json"
        init_state(sf, "deleg-mismatch")
        bad = issue_receipt("10", "orchestrator/deployer", "tok-10")  # 阶段10应为 orchestrator/notifier
        try:
            register_receipt(sf, bad)
            assert False, "应抛 ValueError"
        except ValueError as e:
            assert "subagent 不匹配" in str(e), e
        # 正确 subagent 仍可正常登记
        good = issue_receipt("10", "orchestrator/notifier", "tok-10")
        register_receipt(sf, good)
