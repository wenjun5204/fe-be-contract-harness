#!/usr/bin/env python3
"""轻量代码知识图:符号索引 / 定义 / 引用查询(替代 grep 的结构化检索)。

设计:regex 提取声明 + 引用(非完整 AST,但确定性、零依赖、跨语言)。
支持 TS/JS/Java/Python 的常见声明形态。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "target", ".idea", ".vscode", ".agents"}
SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".java", ".py"}

DECL_PATTERNS = [
    ("class", re.compile(r'\b(?:export\s+)?(?:abstract\s+)?class\s+(\w+)')),
    ("interface", re.compile(r'\b(?:export\s+)?interface\s+(\w+)')),
    ("enum", re.compile(r'\b(?:export\s+)?enum\s+(\w+)')),
    ("function", re.compile(r'\b(?:export\s+)?(?:async\s+)?function\s+(\w+)')),
    ("const", re.compile(r'\bexport\s+const\s+(\w+)')),
    ("type", re.compile(r'\b(?:export\s+)?type\s+(\w+)')),
    ("def", re.compile(r'^\s*def\s+(\w+)', re.MULTILINE)),
]


def _walk(repo: Path):
    for p in repo.rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_SUFFIXES:
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        yield p


def build_index(repo_path: str) -> dict:
    """构建符号索引:{symbol: {defs: [{file,line,kind}], refs: [file]}}。"""
    repo = Path(repo_path)
    symbols: Dict[str, dict] = {}

    for f in _walk(repo):
        text = f.read_text(encoding="utf-8", errors="ignore")
        rel = str(f.relative_to(repo))
        for kind, pat in DECL_PATTERNS:
            for m in pat.finditer(text):
                name = m.group(1)
                line = text[: m.start()].count("\n") + 1
                symbols.setdefault(name, {"defs": [], "refs": []})
                symbols[name]["defs"].append({"file": rel, "line": line, "kind": kind})

    for f in _walk(repo):
        text = f.read_text(encoding="utf-8", errors="ignore")
        rel = str(f.relative_to(repo))
        for name in symbols:
            if name in text:
                symbols[name]["refs"].append(rel)

    return {"repo": str(repo), "symbols": symbols}


def find_definition(index: dict, symbol: str) -> List[dict]:
    return index.get("symbols", {}).get(symbol, {}).get("defs", [])


def find_references(index: dict, symbol: str) -> List[str]:
    return index.get("symbols", {}).get(symbol, {}).get("refs", [])


def list_symbols(index: dict, kind: Optional[str] = None) -> List[str]:
    if kind:
        return sorted(s for s, v in index.get("symbols", {}).items()
                      if any(d["kind"] == kind for d in v["defs"]))
    return sorted(index.get("symbols", {}).keys())


def query(index: dict, symbol: str) -> dict:
    """组合查询:定义 + 引用文件 + 影响面风险。"""
    defs = find_definition(index, symbol)
    refs = find_references(index, symbol)
    risk = "high" if len(defs) > 1 or len(refs) > 20 else ("medium" if refs else "low")
    return {"symbol": symbol, "definitions": defs, "reference_files": refs, "risk": risk}


def main(argv=None) -> int:
    import argparse
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="轻量代码知识图")
    sub = p.add_subparsers(dest="cmd")

    b = sub.add_parser("build", help="构建符号索引")
    b.add_argument("repo")
    b.add_argument("--out", default=None, help="输出 JSON 文件")

    q = sub.add_parser("query", help="查询符号定义/引用")
    q.add_argument("repo")
    q.add_argument("symbol")

    args = p.parse_args(argv)
    if args.cmd == "build":
        index = build_index(args.repo)
        print(json.dumps({"repo": index["repo"], "symbol_count": len(index["symbols"])}, ensure_ascii=False))
        if args.out:
            Path(args.out).write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    elif args.cmd == "query":
        index = build_index(args.repo)
        print(json.dumps(query(index, args.symbol), ensure_ascii=False, indent=2))
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
