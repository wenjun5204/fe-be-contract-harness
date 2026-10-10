#!/usr/bin/env python3
"""覆盖率采集适配器:跑覆盖率命令 → 解析输出 → 喂门控。

解析部分确定性可测;跑命令部分薄封装(subprocess)。
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional


def parse_line_coverage(output: str) -> Optional[float]:
    """从覆盖率输出提取行覆盖率 %。支持 vitest/jest(istanbul)/jacoco 常见格式。"""
    patterns = [
        r'All files\s*\|\s*[\d.]+\s*\|\s*[\d.]+\s*\|\s*[\d.]+\s*\|\s*([\d.]+)',  # jest/vitest table
        r'Lines?\s*:\s*([\d.]+)%',
        r'([\d.]+)%\s*Stmts',  # istanbul
        r'Total\s*.*?([\d.]+)%',  # jacoco
    ]
    for p in patterns:
        m = re.search(p, output)
        if m:
            return float(m.group(1))
    return None


def parse_report(stack: str, output: str) -> dict:
    """解析覆盖率输出 → {changed_line, new_file, delta_drop}(尽力而为)。"""
    return {"changed_line": parse_line_coverage(output), "new_file": None, "delta_drop": None}


def collect(stack: str, repo_path: str) -> dict:
    """跑覆盖率命令并解析(薄封装)。"""
    from lib.stack.adapter import get_adapter
    adapter = get_adapter(stack)
    cmd = adapter.coverage_command()
    if not cmd:
        return {"error": f"{stack} 无覆盖率命令"}
    try:
        result = subprocess.run(cmd, shell=True, cwd=repo_path, capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        return {"stack": stack, "command": cmd, "report": parse_report(stack, output), "exit": result.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "覆盖率命令超时"}


def check(stack: str, repo_path: str) -> dict:
    """采集 + 门控。"""
    collected = collect(stack, repo_path)
    if "error" in collected:
        return {"ok": False, "error": collected["error"]}
    from lib.coverage_gate import check_coverage
    gate = check_coverage(collected["report"])
    return {"collected": collected, "gate": gate, "ok": gate["ok"]}


if __name__ == "__main__":
    import argparse
    import json
    import sys
    p = argparse.ArgumentParser(description="覆盖率采集")
    p.add_argument("stack")
    p.add_argument("repo")
    p.add_argument("--check", action="store_true", help="采集后直接门控")
    args = p.parse_args()
    result = check(args.stack, args.repo) if args.check else collect(args.stack, args.repo)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok", True) else 1)
