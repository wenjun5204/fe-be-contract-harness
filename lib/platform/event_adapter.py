#!/usr/bin/env python3
"""平台事件 envelope 适配层(第一阶段 C)—— 把各 Agent 平台的原始事件统一为 hook 标准 envelope。

背景:hooks/*-guard 从 stdin 读「标准事件 envelope」(见 lib/hook_protocol.py),
但真实运行时(CatPaw/CatClaw/Claude Code/Codex/OpenClaw/OpenCode)的
tool:before/tool:after 事件 payload 是平台自定义的。本模块负责:

    平台原始事件  →  normalize()  →  标准 envelope(hook 可消费)

标准 envelope(字段全集,按需出现):
{
  "event": "tool:before" | "tool:after" | "session_start" | ...,
  "platform": "openclaw" | "claude-code" | "catpaw" | "catclaw" | "codex" | "opencode" | "generic",
  "tool": "git_commit" | "Edit" | "Bash" | ...,
  "stage": "5A",              # 状态阶段(委派/checkpoint/完成场景)
  "state_file": "state.json",
  "contract": "examples/petstore.yaml",
  "stack": "node",
  "gen_dir": "gen/node",
  "file_path": "src/api.ts",
  "receipt": {...},
  "outputs": {...},
  "checkpoint_decision": "approve",
  "evidence": [...],
  "report": {...}
}

⚠️ 接线状态(第一阶段):本模块提供「尽力提取」的 normalize,供平台运行时适配器调用;
真实平台事件 → envelope 的精确映射需要在各平台运行时上验证后固化(README「现状与边界」)。
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

# hook 关心的字段(顶层可识别键)
KNOWN_FIELDS = (
    "event", "stage", "state_file", "contract", "stack", "gen_dir",
    "file_path", "receipt", "outputs", "checkpoint_decision", "evidence", "report",
)


def _extract_event(ev: dict) -> str:
    for k in ("event", "type", "kind"):
        v = ev.get(k)
        if isinstance(v, str):
            return v
    return "tool:before" if "tool" in ev or "tool_name" in ev or "name" in ev else "generic"


def _extract_tool(ev: dict) -> Optional[str]:
    for k in ("tool", "tool_name", "toolName", "name"):
        v = ev.get(k)
        if isinstance(v, str):
            return v
    # 某些平台把工具名放 input 里
    inp = ev.get("input") or ev.get("tool_input") or ev.get("arguments") or {}
    if isinstance(inp, dict):
        for k in ("tool", "name"):
            if isinstance(inp.get(k), str):
                return inp[k]
    return None


def _extract_input(ev: dict) -> dict:
    inp = ev.get("input") or ev.get("tool_input") or ev.get("arguments") or {}
    return inp if isinstance(inp, dict) else {}


def _pick(ev: dict, *keys, default=None):
    for k in keys:
        if k in ev and ev[k] is not None:
            return ev[k]
    return default


def normalize(platform: str = "generic", event: Optional[dict] = None, **kwargs) -> dict:
    """平台原始事件 → 标准 envelope(尽力提取,未知字段透传)。"""
    ev = dict(event or {})
    ev.update({k: v for k, v in kwargs.items() if v is not None})

    env: Dict[str, Any] = {
        "platform": platform,
        "event": _extract_event(ev),
        "tool": _extract_tool(ev),
    }
    inp = _extract_input(ev)

    # 直接字段优先,其次工具 input,再次兜底透传
    env["stage"] = _pick(ev, "stage", default=inp.get("stage"))
    env["state_file"] = _pick(ev, "state_file", "state", default=inp.get("state_file", inp.get("state")))
    env["contract"] = _pick(ev, "contract", default=inp.get("contract"))
    env["stack"] = _pick(ev, "stack", default=inp.get("stack"))
    env["gen_dir"] = _pick(ev, "gen_dir", default=inp.get("gen_dir"))
    env["file_path"] = _pick(ev, "file_path", default=inp.get("file_path"))
    env["receipt"] = _pick(ev, "receipt", default=inp.get("receipt"))
    env["outputs"] = _pick(ev, "outputs", default=inp.get("outputs"))
    env["checkpoint_decision"] = _pick(ev, "checkpoint_decision", "response", default=inp.get("checkpoint_decision"))
    env["evidence"] = _pick(ev, "evidence", default=inp.get("evidence"))
    env["report"] = _pick(ev, "report", default=inp.get("report"))

    # 透传其余已知字段与平台元信息
    for k in KNOWN_FIELDS:
        if k not in env and k in ev:
            env[k] = ev[k]
    for k in ("session_id", "sessionId", "workspace", "change_id"):
        if k in ev:
            env[k] = ev[k]

    return {k: v for k, v in env.items() if v is not None}


def main(argv=None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="平台事件 → 标准 envelope 适配")
    p.add_argument("--platform", default="generic")
    p.add_argument("--event-json", help="原始平台事件 JSON(否则读 stdin)")
    args = p.parse_args(argv)
    if args.event_json:
        raw = json.loads(args.event_json)
    else:
        raw = json.load(sys.stdin)
    print(json.dumps(normalize(args.platform, raw), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
