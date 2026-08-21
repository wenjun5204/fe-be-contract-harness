#!/usr/bin/env python3
"""Agent 完整性校验:delegation-policy.json 引用的每个 subagent 都有 agent.json + prompt.md。

运行:python3 lib/validate-agents.py(退出码 0=完整,1=缺失)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
POLICY_PATH = REPO_ROOT / "config" / "delegation-policy.json"

# 不在 stage_subagent 映射里、但作为完整 agent 集应有的定义
EXTRA_AGENTS = [
    "codegen/vue-codegen",
    "codegen/java-codegen",
    "orchestrator/planner",
]


def check_agent(subagent: str) -> dict:
    """subagent 形如 'contract/contract-designer'。"""
    d = AGENTS_DIR / subagent
    agent_json = d / "agent.json"
    if not agent_json.exists():
        return {"ok": False, "reason": f"缺少 {agent_json}"}
    data = json.loads(agent_json.read_text(encoding="utf-8"))
    prompt_file = data.get("prompt_file", "prompt.md")
    prompt_path = d / prompt_file
    if not prompt_path.exists():
        return {"ok": False, "reason": f"缺少 {prompt_path}"}
    return {"ok": True, "name": data.get("name", subagent)}


def validate() -> dict:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    subagents = policy.get("stage_subagent", {})
    problems = []
    checked = []

    for stage, subagent in sorted(subagents.items()):
        r = check_agent(subagent)
        checked.append({"stage": stage, "subagent": subagent, "ok": r["ok"]})
        if not r["ok"]:
            problems.append(f"Stage {stage} ({subagent}): {r['reason']}")

    for subagent in EXTRA_AGENTS:
        r = check_agent(subagent)
        checked.append({"stage": None, "subagent": subagent, "ok": r["ok"]})
        if not r["ok"]:
            problems.append(f"{subagent}: {r['reason']}")

    return {"ok": not problems, "problems": problems, "checked": checked}


def main(argv=None) -> int:
    r = validate()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
