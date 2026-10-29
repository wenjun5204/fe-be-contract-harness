#!/usr/bin/env python3
"""平台适配层自测(P2-2):事件精确映射 + 子 Agent 派发/回传闭环。

覆盖:
- event_adapter:claude-code hook_event_name/tool_name 精确映射、openclaw params
  平铺、generic 透传,以及 hook_protocol --platform 的真实接线
- subagent_dispatch:directive → 任务包(prompt 内嵌门控命令),
  StageResult 回传 → 经 transition 全门控推进(伪造 receipt fail-closed)

运行:python3 tests/test_platform_adapter.py
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.delegation import issue_receipt  # noqa: E402
from lib.hook_protocol import read_event  # noqa: E402
from lib.platform.event_adapter import normalize  # noqa: E402
from lib.platform.subagent_dispatch import apply_stage_result, build_subagent_task  # noqa: E402
from lib.platform.subagent_dispatch import main as dispatch_main  # noqa: E402
from lib.state_manager import init_state, read_state, set_stage_state  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "platform"


def _fixture(path: str) -> dict:
    return json.loads((FIXTURES / path).read_text(encoding="utf-8"))


# ---- event_adapter:claude-code 精确映射(fixture 固化) ----

def test_claude_code_pretooluse_edit():
    ev = normalize("claude-code", _fixture("claude-code/pretooluse-edit.json"))
    assert ev["event"] == "tool:before"
    assert ev["tool"] == "Edit"
    # tool_input.file_path 平铺(pre-edit-guard 直接可消费)
    assert ev["file_path"] == "gen/node/api-client.ts"
    assert ev["session_id"] == "cc-abc123"


def test_claude_code_tool_alias_todowrite():
    """Claude Code 驼峰工具名 → harness 约定(openclaw plugin match 用 todo_write)。"""
    ev = normalize("claude-code", _fixture("claude-code/pretooluse-todowrite.json"))
    assert ev["event"] == "tool:before"
    assert ev["tool"] == "todo_write"


def test_claude_code_sessionstart():
    ev = normalize("claude-code", _fixture("claude-code/sessionstart.json"))
    assert ev["event"] == "session_start"


def test_claude_code_posttooluse_bash():
    ev = normalize("claude-code", _fixture("claude-code/posttooluse-bash.json"))
    assert ev["event"] == "tool:after"
    assert ev["tool"] == "Bash"


def test_hook_protocol_platform_wire():
    """接线验证:hook_protocol.read_event --platform claude-code → event_adapter 精确映射。"""
    ev = read_event([
        "--platform", "claude-code",
        "--event", str(FIXTURES / "claude-code" / "pretooluse-edit.json"),
    ])
    assert ev["event"] == "tool:before"
    assert ev["tool"] == "Edit"
    assert ev["file_path"] == "gen/node/api-client.ts"


# ---- event_adapter:openclaw / generic ----

def test_openclaw_params_flattened():
    ev = normalize("openclaw", _fixture("openclaw/tool-before-commit.json"))
    assert ev["event"] == "tool:before"
    assert ev["tool"] == "git_commit"
    # params 平铺到顶层(contract-drift-guard 直接可消费)
    assert ev["contract"] == "examples/petstore.yaml"
    assert ev["stack"] == "node"
    assert ev["gen_dir"] == "gen/node"


def test_generic_passthrough():
    ev = normalize("generic", {"event": "tool:before", "stage": "5A", "tool": "Edit"})
    assert ev["event"] == "tool:before"
    assert ev["stage"] == "5A"
    assert ev["tool"] == "Edit"


def test_event_adapter_cli():
    """CLI:--platform claude-code --event <fixture 文件> → 标准 envelope。"""
    from lib.platform.event_adapter import main as adapter_main
    with contextlib.redirect_stdout(io.StringIO()) as out:
        rc = adapter_main([
            "--platform", "claude-code",
            "--event", str(FIXTURES / "claude-code" / "pretooluse-edit.json"),
        ])
    assert rc == 0
    env = json.loads(out.getvalue())
    assert env["event"] == "tool:before"
    assert env["tool"] == "Edit"
    assert env["file_path"] == "gen/node/api-client.ts"


# ---- subagent_dispatch:任务包构建 ----

def _directive(stage="2", sub="contract/contract-designer", token="platform-test"):
    receipt = issue_receipt(stage, sub, token)
    return {
        "stage": stage,
        "subagent": sub,
        "subagents": [sub],
        "receipt": receipt,
        "contract": "examples/petstore.yaml",
        "context": {"text": "stage=2; entities=Pet", "schema": "dispatch-context/v1"},
    }


def test_build_subagent_task():
    task = build_subagent_task(_directive(), "state.json", harness_root=REPO)
    assert task["schema"] == "subagent-task/v1"
    assert task["stage"] == "2"
    assert task["subagent"] == "contract/contract-designer"
    assert task["required_outputs"] == ["openapi_contract"]
    # receipt 原样保留(回传时使用,README 适配器五步之 3)
    assert task["receipt"]["token"] == "platform-test"
    # prompt 注入角色职责(agents/<sub>/prompt.md)+ 门控纪律 + transition 命令
    assert "接口契约设计专家" in task["prompt"]
    assert "绝不要直接编辑 state.json" in task["prompt"]
    assert "lib/transition.py register" in task["prompt"]
    assert "lib/transition.py complete" in task["prompt"]
    assert "openapi_contract" in task["prompt"]
    assert task["receipt"] and json.dumps(task["receipt"]) in task["prompt"]


# ---- subagent_dispatch:StageResult 回传(经 transition 全门控) ----

def _state_with_prereqs(d, stage):
    """构造 stage 前置全部终态的 state,使该 stage 可 start。"""
    sf = Path(d) / "state.json"
    init_state(sf, "platform-test")
    order = ["0", "1", "2", "3", "4", "5A", "5B", "6", "7", "8", "9", "10"]
    for sid in order[:order.index(stage)]:
        set_stage_state(sf, sid, "completed")
    return sf


def test_apply_stage_result_completes_via_gates():
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d, "4")
        directive = _directive(stage="4", sub="orchestrator/git-client")
        payload = {
            "stage": "4",
            "receipt": directive["receipt"],
            "outputs": {"branch_name": "feat/platform-adapter"},
            "evidence": [{"type": "platform_result", "detail": "subagent=orchestrator/git-client"}],
        }
        res = apply_stage_result(sf, payload)
        assert res["ok"], res
        assert res["status"] == "completed", res
        st = read_state(sf)["stages"]
        assert st["4"]["state"] == "completed", st["4"]
        assert st["4"]["outputs"]["branch_name"] == "feat/platform-adapter", st["4"]
        # receipt 已登记且一次性消费
        assert read_state(sf)["receipts"]["4"]["used"]
        assert st["4"]["evidence"][0]["type"] == "platform_result"


def test_apply_stage_result_tampered_receipt_fail_closed():
    """receipt 的 stage 与 payload 不一致(张冠李戴)→ blocked,状态不被推进。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d, "4")
        receipt = issue_receipt("3", "orchestrator/services-analyst", "attacker")
        res = apply_stage_result(sf, {
            "stage": "4", "receipt": receipt, "outputs": {"branch_name": "x"},
        })
        assert not res["ok"] and res["status"] == "blocked", res
        assert any("不匹配" in r for r in res["reasons"]), res["reasons"]
        assert read_state(sf)["stages"]["4"]["state"] == "pending"  # 未被推进


def test_apply_stage_result_missing_outputs_gate_blocked():
    """receipt 合法但 outputs 缺必需键 → gate_blocked,阶段留 running,不伪造终态。"""
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d, "4")
        directive = _directive(stage="4", sub="orchestrator/git-client")
        res = apply_stage_result(sf, {
            "stage": "4", "receipt": directive["receipt"], "outputs": {},
        })
        assert not res["ok"] and res["status"] == "gate_blocked", res
        assert res["reasons"], res
        assert read_state(sf)["stages"]["4"]["state"] == "running"  # 已 start 未过门


def test_subagent_dispatch_cli():
    with tempfile.TemporaryDirectory() as d:
        sf = _state_with_prereqs(d, "4")
        directive = _directive(stage="4", sub="orchestrator/git-client")
        # task:directive → 任务包
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = dispatch_main(["task", "--directive-json", json.dumps(directive), "--state", str(sf)])
        assert rc == 0
        task = json.loads(out.getvalue())
        assert task["schema"] == "subagent-task/v1"
        # result:回传 → 经门控完成
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = dispatch_main(["result", "--state", str(sf), "--payload-json", json.dumps({
                "stage": "4",
                "receipt": directive["receipt"],
                "outputs": {"branch_name": "feat/cli"},
            })])
        assert rc == 0, out.getvalue()
        assert read_state(sf)["stages"]["4"]["state"] == "completed"


def main():
    test_claude_code_pretooluse_edit()
    test_claude_code_tool_alias_todowrite()
    test_claude_code_sessionstart()
    test_claude_code_posttooluse_bash()
    test_hook_protocol_platform_wire()
    test_openclaw_params_flattened()
    test_generic_passthrough()
    test_event_adapter_cli()
    test_build_subagent_task()
    test_apply_stage_result_completes_via_gates()
    test_apply_stage_result_tampered_receipt_fail_closed()
    test_apply_stage_result_missing_outputs_gate_blocked()
    test_subagent_dispatch_cli()
    print("OK: platform adapter 自测通过(13 组断言)")


if __name__ == "__main__":
    main()
