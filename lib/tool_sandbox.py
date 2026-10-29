#!/usr/bin/env python3
"""执行类工具沙箱(P2-5)—— 白名单命令 + 无 shell + 超时 + 输出截断。

CAPABILITIES 第 3 层「执行类工具隔离」的落地。三条安全边界:

1. **白名单**:命令来自各栈 adapter 的 LINT/BUILD/TEST 常量(项目自带数据,
   LLM 不可控)。模型只能选择 kind(lint/build/test)与 stack,不能传入自定义
   命令、参数或 shell 片段——run_check 工具的参数 schema 根本没有命令字段。
2. **无 shell**:subprocess list-args(不走 shell=True,天然免疫 shell 注入);
   白名单命令本身若含 shell 元字符(数据被篡改的形态)即拒绝执行,fail-closed。
3. **超时 + 输出截断**:超时 kill(默认 120s,上限 600s);输出保留头 2000 +
   尾 1000 字符,中间省略并注明(ACI:输出紧凑,防撑爆上下文)。

超时/命令缺失/非零退出都是**正常返回**(交回模型自纠错或作为失败证据),
只有白名单配置本身异常(元字符/未知 kind)才抛 SandboxError(由工具层收敛
为 ok=false)。

用法(LLM 工具侧入口见 tool_registry 的 run_check):
    from lib.tool_sandbox import run_whitelisted
    run_whitelisted("test", "node", workdir=Path(repo))
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import List

KINDS = ("lint", "build", "test")
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600
OUTPUT_HEAD_CHARS = 2000
OUTPUT_TAIL_CHARS = 1000

# 白名单命令绝不允许的形态(出现即数据被篡改,拒绝执行)
_FORBIDDEN_FRAGMENTS = ("&&", "||", "|", ";", ">", "<", "$(", "`", "\n", "\x00")


class SandboxError(Exception):
    """沙箱配置类错误(白名单命令非法 / kind 未知),fail-closed 抛出。"""


def _resolve_commands(kind: str, stack: str) -> List[str]:
    """从栈 adapter 白名单解析命令列表(数据源,LLM 不可控)。"""
    from lib.stack.adapter import get_adapter
    adapter = get_adapter(stack)
    if kind == "lint":
        return adapter.lint_commands()
    if kind == "build":
        return adapter.build_commands()
    if kind == "test":
        return adapter.test_commands()
    raise SandboxError(f"未知 kind: {kind}(可选: {', '.join(KINDS)})")


def _to_argv(command: str) -> List[str]:
    """白名单命令字符串 → list-args。含 shell 元字符即拒绝(无 shell 执行)。"""
    for frag in _FORBIDDEN_FRAGMENTS:
        if frag in command:
            raise SandboxError(f"白名单命令含 shell 元字符,拒绝执行(疑似数据被篡改): {command!r}")
    argv = command.split()
    if not argv:
        raise SandboxError(f"白名单命令为空: {command!r}")
    return argv


def _truncate_output(text: str) -> tuple:
    """输出截断:保头保尾,中间省略并注明(ACI:输出紧凑)。返回 (text, truncated)。"""
    text = (text or "").strip()
    if len(text) <= OUTPUT_HEAD_CHARS + OUTPUT_TAIL_CHARS:
        return text, False
    elided = len(text) - OUTPUT_HEAD_CHARS - OUTPUT_TAIL_CHARS
    return (
        text[:OUTPUT_HEAD_CHARS]
        + f"\n...[elided {elided} chars]...\n"
        + text[-OUTPUT_TAIL_CHARS:],
        True,
    )


def run_whitelisted(
    kind: str,
    stack: str,
    workdir: str | Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """在 workdir 内按序执行白名单命令(lint/build/test)。

    返回:
    {"ok": bool(全部命令退出码为 0), "kind", "stack",
     "exit_code": 首个非零退出码(全过为 0,可作 evidence),
     "duration_seconds": 总耗时,
     "results": [{"command", "exit_code", "output"(截断), "truncated",
                  "duration_seconds", "timeout"?, "error"?}, ...]}
    超时被 kill / 命令不存在 → 该条 result 带 timeout/error 标记,ok=False。
    """
    timeout = max(1, min(int(timeout), MAX_TIMEOUT_SECONDS))
    workdir = Path(workdir)
    commands = _resolve_commands(kind, stack)
    if not commands:
        return {"ok": False, "kind": kind, "stack": stack,
                "error": f"{stack} 无 {kind} 白名单命令"}

    results: List[dict] = []
    exit_code = 0
    started = time.monotonic()
    for command in commands:
        argv = _to_argv(command)
        entry: dict = {"command": command}
        cmd_started = time.monotonic()
        try:
            proc = subprocess.run(
                argv, cwd=str(workdir), capture_output=True, text=True, timeout=timeout,
            )
            output, truncated = _truncate_output(proc.stdout + "\n" + proc.stderr)
            entry.update({
                "exit_code": proc.returncode,
                "output": output,
                "truncated": truncated,
                "duration_seconds": round(time.monotonic() - cmd_started, 2),
            })
            if proc.returncode != 0 and exit_code == 0:
                exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            entry.update({
                "timeout": True,
                "error": f"超时(>{timeout}s)被 kill",
                "duration_seconds": round(time.monotonic() - cmd_started, 2),
            })
            exit_code = exit_code or 124
        except FileNotFoundError:
            entry.update({
                "error": f"命令不存在: {argv[0]}(环境未安装?)",
                "duration_seconds": round(time.monotonic() - cmd_started, 2),
            })
            exit_code = exit_code or 127
        results.append(entry)

    return {
        "ok": exit_code == 0,
        "kind": kind,
        "stack": stack,
        "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started, 2),
        "results": results,
    }
