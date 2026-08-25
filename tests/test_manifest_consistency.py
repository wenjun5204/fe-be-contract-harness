#!/usr/bin/env python3
"""manifest ↔ hooks/agents/skills 一致性自测(第一阶段 D)。

校验:
1. openclaw.plugin.json 声明的 hooks 文件都存在且可执行
2. 声明的 skills / agents_dir / commands_dir / lib_dir 存在
3. harness-manifest.json 的 health_check handler 存在
4. delegation-policy.json 的 stage_subagent 全部有对应 agent.json
5. workflow-dag.json 的阶段与 delegation-policy 的 stage_subagent 一一对应

运行:python3 tests/test_manifest_consistency.py   (pytest tests/ 亦可收集)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_hooks_declared_exist_and_executable():
    plugin = _load("openclaw.plugin.json")
    for h in plugin.get("hooks", []):
        p = ROOT / h["path"]
        assert p.exists(), f"hook 文件缺失: {h['path']}"
        assert os.access(p, os.X_OK), f"hook 不可执行: {h['path']}"


def test_skills_agents_commands_declared_exist():
    plugin = _load("openclaw.plugin.json")
    for s in plugin.get("skills", []):
        assert (ROOT / s["path"]).exists(), f"skill 缺失: {s['path']}"
    for d in ("agents_dir", "commands_dir", "lib_dir"):
        assert (ROOT / plugin[d]).is_dir(), f"{d} 缺失: {plugin[d]}"


def test_health_check_handler_exists():
    manifest = _load("harness-manifest.json")
    handler = manifest.get("lifecycle", {}).get("health_check", {}).get("handler")
    assert handler, "harness-manifest 缺少 health_check.handler"
    assert (ROOT / handler).exists(), f"health_check handler 缺失: {handler}"


def test_delegation_subagents_have_agent_json():
    policy = _load("config/delegation-policy.json")
    for stage, configured in policy.get("stage_subagent", {}).items():
        if isinstance(configured, str):
            subagents = [configured]
        else:
            subagents = list(configured.get("by_stack", {}).values())
            skip_subagent = configured.get("skip_subagent")
            if skip_subagent:
                subagents.append(skip_subagent)
        for sub in set(subagents):
            d = ROOT / "agents" / sub
            assert (d / "agent.json").exists(), f"stage {stage} 的 subagent 无 agent.json: {sub}"
            assert (d / "prompt.md").exists(), f"stage {stage} 的 subagent 无 prompt.md: {sub}"


def test_dag_and_policy_stages_align():
    dag = _load("lib/workflow-dag.json")
    policy = _load("config/delegation-policy.json")
    dag_stages = set(dag["stage_graph"].keys())
    policy_stages = set(policy["stage_subagent"].keys())
    assert dag_stages == policy_stages, (
        f"DAG 阶段与委派策略不一致:\n  DAG 独有: {sorted(dag_stages - policy_stages)}\n"
        f"  policy 独有: {sorted(policy_stages - dag_stages)}"
    )


def test_state_schema_receipts_field():
    schema = _load("lib/state-schemas.json")
    assert "receipts" in schema["properties"], "state-schemas 缺少 receipts 登记表字段"


def main():
    test_hooks_declared_exist_and_executable()
    test_skills_agents_commands_declared_exist()
    test_health_check_handler_exists()
    test_delegation_subagents_have_agent_json()
    test_dag_and_policy_stages_align()
    test_state_schema_receipts_field()
    print("OK: manifest 一致性自测通过(6 组断言)")


if __name__ == "__main__":
    main()
