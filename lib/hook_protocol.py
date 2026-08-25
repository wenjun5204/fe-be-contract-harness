#!/usr/bin/env python3
"""hook 统一协议 —— 事件上下文经 stdin / --event 输入,结果以机器可读 JSON 输出(第一阶段)。

协议:
- 输入(优先级):
    1. --event <path>        从文件读 JSON
    2. --event-json <json>   直接传 JSON 字符串
    3. 位置参数(旧协议)      各 hook 通过 from_args 映射为事件 dict
    4. stdin(非 TTY 且有内容) 从管道读 JSON
- 输出(stdout): {"allow": bool, "code"?, "message"?, ...} + 退出码(0 放行 / 1 阻断 / 2 协议错误)

用途:所有 hooks/*-guard 统一从 stdin 读平台事件 envelope(见 openclaw.plugin.json),
不再依赖隐式位置参数,保证跨 CatPaw/CatClaw/Claude Code/OpenClaw 等平台一致。
"""
from __future__ import annotations

import json
import sys
from typing import Callable, Dict, List, Optional


class UsageError(Exception):
    """事件上下文缺失或协议错误。"""


def _strip_options(argv: List[str]) -> List[str]:
    """剔除 --event/--event-json/--platform 及其值,保留纯位置参数(旧协议)。"""
    out: List[str] = []
    skip_next = False
    for a in argv:
        if skip_next:
            skip_next = False
            continue
        if a in ("--event", "--event-json", "--platform"):
            skip_next = True
            continue
        out.append(a)
    return out


def read_event(argv: Optional[List[str]] = None, from_args: Optional[Callable[[List[str]], dict]] = None) -> dict:
    """读取事件上下文 dict。from_args 为旧位置参数 → dict 的映射函数(可为 None 表示不支持)。

    --platform <name> 时对读入事件做 normalize(平台原始事件 → 标准 envelope,见 lib/platform/event_adapter.py)。
    """
    argv = list(argv or [])
    platform = None
    if "--platform" in argv:
        i = argv.index("--platform")
        if i + 1 < len(argv):
            platform = argv[i + 1]

    if "--event" in argv:
        i = argv.index("--event")
        if i + 1 >= len(argv):
            raise UsageError("--event 缺少文件路径")
        with open(argv[i + 1], "r", encoding="utf-8") as f:
            ev = json.load(f)
        return _normalize(platform, ev)

    if "--event-json" in argv:
        i = argv.index("--event-json")
        if i + 1 >= len(argv):
            raise UsageError("--event-json 缺少 JSON")
        return _normalize(platform, json.loads(argv[i + 1]))

    # 旧位置参数协议
    positional = _strip_options(argv)
    if positional:
        if from_args is None:
            raise UsageError("该 hook 不支持位置参数,请通过 --event-json 传入事件")
        return from_args(positional)

    # stdin 管道输入(非 TTY)
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return _normalize(platform, json.loads(data))

    raise UsageError("缺少事件上下文(请通过 stdin / --event / --event-json 传入 JSON)")


def _normalize(platform: Optional[str], ev: dict) -> dict:
    if not platform:
        return ev
    from lib.platform.event_adapter import normalize
    return normalize(platform, ev)


def emit(result: dict) -> int:
    """输出结果 JSON,返回退出码(0 放行 / 1 阻断)。"""
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("allow", True) else 1


def block(code: str, message: str, **extra) -> dict:
    return {"allow": False, "code": code, "message": message, **extra}


def allow(**extra) -> dict:
    return {"allow": True, **extra}
