#!/usr/bin/env python3
"""hooks 统一 JSON event protocol 自测(第一阶段)。

验证每个 hooks/*-guard 从 stdin 读事件 JSON、输出 {"allow", ...}、退出码 0/1。
运行:python3 tests/test_hooks_protocol.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.state_manager import init_state  # noqa: E402

HOOKS = Path(__file__).resolve().parent.parent / "hooks"


def run_hook(name: str, event: dict) -> tuple:
    """调用 hook,返回 (exit_code, result_dict)。"""
    p = subprocess.run(
        [str(HOOKS / name)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=str(HOOKS.parent),
    )
    try:
        result = json.loads(p.stdout)
    except json.JSONDecodeError:
        result = {"stdout": p.stdout, "stderr": p.stderr}
    return p.returncode, result


def test_delegation_guard():
    code, r = run_hook("delegation-guard", {"stage": "2", "receipt": None, "outputs": {"openapi_contract": "x"}})
    assert code != 0 and r["allow"] is False and r["code"] == "DELEGATION_BLOCKED", (code, r)
    receipt = {"schema": "stage-subagent/v1", "stage": "2", "subagent": "contract/contract-designer", "token": "t"}
    code, r = run_hook("delegation-guard", {"stage": "2", "receipt": receipt, "outputs": {"openapi_contract": "x"}})
    assert code == 0 and r["allow"] is True, (code, r)


def test_checkpoint_guard():
    # mandatory_review 不可 skip
    code, r = run_hook("checkpoint-guard", {"stage": "2", "response": "skip"})
    assert code != 0 and r["allow"] is False, (code, r)
    # approve 放行
    code, r = run_hook("checkpoint-guard", {"stage": "2", "response": "approve"})
    assert code == 0 and r["allow"] is True and r["decision"] == "approve", (code, r)


def test_coverage_guard():
    code, r = run_hook("coverage-guard", {"report": {"changed_line": 45.0}})
    assert code != 0 and r["allow"] is False and r["code"] == "COVERAGE_BLOCKED", (code, r)
    code, r = run_hook("coverage-guard", {"report": {"changed_line": 75.0}})
    assert code == 0 and r["allow"] is True, (code, r)
    # 直接字段形式
    code, r = run_hook("coverage-guard", {"changed_line": 75.0})
    assert code == 0 and r["allow"] is True, (code, r)


def test_pre_edit_guard():
    # 普通文件放行
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "a.ts"
        f.write_text("export const a = 1;", encoding="utf-8")
        code, r = run_hook("pre-edit-guard", {"file_path": str(f)})
        assert code == 0 and r["allow"] is True, (code, r)
        # 契约文件名阻断
        f2 = Path(d) / "openapi.yaml"
        f2.write_text("openapi: 3.0.0\npaths: {}\n", encoding="utf-8")
        code, r = run_hook("pre-edit-guard", {"file_path": str(f2)})
        assert code != 0 and r["allow"] is False and r["code"] == "PROTECTED_FILE", (code, r)
        # 生成区「勿手改」文件阻断
        f3 = Path(d) / "gen" / "api.ts"
        f3.parent.mkdir()
        f3.write_text("// 勿手改\n", encoding="utf-8")
        code, r = run_hook("pre-edit-guard", {"file_path": str(f3)})
        assert code != 0 and r["allow"] is False, (code, r)
        # allow_generated 放行
        code, r = run_hook("pre-edit-guard", {"file_path": str(f3), "allow_generated": True})
        assert code == 0 and r["allow"] is True, (code, r)


def test_drift_guard():
    contract = str(Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml")
    with tempfile.TemporaryDirectory() as d:
        code, r = run_hook("contract-drift-guard", {"contract": contract, "stack": "node", "gen_dir": d})
        assert code != 0 and r["allow"] is False and r["code"] == "CONTRACT_DRIFT", (code, r)


def test_dep_guard():
    code, r = run_hook("dep-guard", {})
    assert code == 0 and r["allow"] is True, (code, r)


def test_stage_completed_integration():
    """stage-completed 走唯一 transition:缺 receipt 阻断;checkpoint 阶段无 decision 停在 checkpoint_pending。"""
    with tempfile.TemporaryDirectory() as d:
        sf = Path(d) / "state.json"
        init_state(sf, "hook-test")
        # 1. 缺 receipt → TRANSITION_BLOCKED
        code, r = run_hook("stage-completed", {
            "state_file": str(sf), "stage": "0",
            "outputs": {"execution_plan": "plan"},
        })
        assert code != 0 and r["code"] == "TRANSITION_BLOCKED", (code, r)
        # 2. 带合法 receipt → completed,next 指向 1
        receipt = {"schema": "stage-subagent/v1", "stage": "0", "subagent": "orchestrator/init", "token": "hook"}
        code, r = run_hook("stage-completed", {
            "state_file": str(sf), "stage": "0",
            "outputs": {"execution_plan": "plan"},
            "receipt": receipt,
            "evidence": [{"type": "contract", "detail": "x.yaml", "at": "t"}],
        })
        assert code == 0 and r["allow"] is True and r["status"] == "completed", (code, r)
        assert r["next"] == ["1"], r
        # 3. Stage 1 mandatory_review 无 decision → checkpoint_pending(allow,等待人工)
        receipt1 = {"schema": "stage-subagent/v1", "stage": "1", "subagent": "orchestrator/requirements-analyst", "token": "hook"}
        outputs1 = {
            "requirements_doc": "doc",
            "requirements_spec": {
                "status": "approved",
                "scope": {"complexity": "M"},
                "clarification": {"unresolved_questions": [], "coverage": {c: "covered" for c in
                    ["goal_value", "users_permissions", "scope", "main_flow", "state", "data",
                     "exceptions", "interaction", "dependencies", "non_functional", "acceptance"]}},
                "contract_readiness": {
                    "entities": [{"name": "Pet", "fields": [{"name": "id", "type": "integer"}]}],
                    "error_codes": [{"code": "404", "meaning": "nf"}]},
                "document": {"approved": True, "quality_gate": "passed"},
            },
            "requirements_quality_gate": "pass",
            "requirements_confirmation_status": "confirmed",
        }
        code, r = run_hook("stage-completed", {
            "state_file": str(sf), "stage": "1",
            "outputs": outputs1,
            "receipt": receipt1,
        })
        assert code == 0 and r["allow"] is True and r["status"] == "checkpoint_pending", (code, r)


def main():
    test_delegation_guard()
    test_checkpoint_guard()
    test_coverage_guard()
    test_pre_edit_guard()
    test_drift_guard()
    test_dep_guard()
    test_stage_completed_integration()
    print("OK: hooks 协议自测通过(7 组断言)")


if __name__ == "__main__":
    main()
