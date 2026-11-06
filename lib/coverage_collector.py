#!/usr/bin/env python3
"""覆盖率采集适配器:跑覆盖率命令 → 解析输出 → 喂门控。

解析部分确定性可测;跑命令部分薄封装(subprocess)。
"""
from __future__ import annotations

import csv
import io
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# 使 `python3 lib/coverage_collector.py` 直接执行时也能 import lib.* 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# jacoco csv 报告路径(maven 约定;java 栈 coverage 命令产出)
JACOCO_CSV_RELPATH = Path("target") / "site" / "jacoco" / "jacoco.csv"


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


def parse_jacoco_csv(csv_text: str) -> Optional[float]:
    """jacoco.csv → 全局行覆盖率 %(真实首跑发现:java 栈 jacoco 控制台输出
    无百分比文本可解析,权威数据在 csv 报告文件)。

    行覆盖 = sum(LINE_COVERED) / (sum(LINE_COVERED) + sum(LINE_MISSED))。
    空表/无行数据返回 None(fail-closed 语义由上层兜底)。
    """
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    covered = sum(int(r["LINE_COVERED"]) for r in rows if r.get("LINE_COVERED", "").isdigit())
    missed = sum(int(r["LINE_MISSED"]) for r in rows if r.get("LINE_MISSED", "").isdigit())
    if covered + missed == 0:
        return None
    return round(100.0 * covered / (covered + missed), 1)


def parse_report(stack: str, output: str) -> dict:
    """解析覆盖率输出 → {changed_line, new_file, delta_drop}(尽力而为)。"""
    return {"changed_line": parse_line_coverage(output), "new_file": None, "delta_drop": None}


def collect(stack: str, repo_path: str) -> dict:
    """跑覆盖率命令并解析(薄封装)。"""
    from lib.stack.adapter import get_adapter
    adapter = get_adapter(stack)
    cmd = adapter.coverage_command(repo_path)
    if not cmd:
        return {"error": f"{stack} 无覆盖率命令"}
    try:
        result = subprocess.run(cmd, shell=True, cwd=repo_path, capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        report = parse_report(stack, output)
        # java 栈权威口径:jacoco csv 报告(控制台无百分比文本);csv 解析
        # 成功时覆盖文本口径,失败回落文本(尽力而为不阻断)。
        csv_path = Path(repo_path) / JACOCO_CSV_RELPATH
        if stack == "java" and csv_path.is_file():
            try:
                pct = parse_jacoco_csv(csv_path.read_text(encoding="utf-8", errors="replace"))
                if pct is not None:
                    report["changed_line"] = pct
            except OSError:
                pass
        return {"stack": stack, "command": cmd, "report": report, "exit": result.returncode}
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
