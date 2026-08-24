#!/usr/bin/env python3
"""经验沉淀 + 自进化骨架:结构化记录经验,供后续 agent 检索。

分类:review(评审经验)/ delivery(交付经验)/ error(错误经验)/ general。
设计:markdown 追加式日志,零依赖;CLI 供 agent 通过 bash 调用。
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIENCE_DIR = REPO_ROOT / "config" / "experience"

CATEGORIES = ("review", "delivery", "error", "general")


def _dir(category: str, root: Optional[Path] = None) -> Path:
    d = (root or EXPERIENCE_DIR) / category
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(category: str, content: str, source: str = "", root: Optional[Path] = None) -> Path:
    """追加一条经验。"""
    if category not in CATEGORIES:
        raise ValueError(f"未知分类: {category},允许 {CATEGORIES}")
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"## {ts} ({source})\n\n{content}\n\n"
    path = _dir(category, root) / "log.md"
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)
    return path


def query(keyword: str, category: Optional[str] = None, root: Optional[Path] = None) -> List[dict]:
    """关键词检索经验。"""
    hits = []
    cats = [category] if category else list(CATEGORIES)
    for c in cats:
        d = _dir(c, root)
        for f in sorted(d.glob("*.md")):
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if keyword.lower() in line.lower():
                    hits.append({"category": c, "file": f.name, "line": i, "text": line.strip()})
    return hits


def load(category: str, root: Optional[Path] = None) -> str:
    parts = [f.read_text(encoding="utf-8") for f in sorted(_dir(category, root).glob("*.md"))]
    return "\n\n".join(parts)


def main(argv=None) -> int:
    import argparse
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="经验沉淀")
    sub = p.add_subparsers(dest="cmd")

    l = sub.add_parser("log", help="追加经验")
    l.add_argument("category")
    l.add_argument("content")
    l.add_argument("--source", default="")

    q = sub.add_parser("query", help="检索经验")
    q.add_argument("keyword")
    q.add_argument("--category", default=None)

    args = p.parse_args(argv)
    if args.cmd == "log":
        path = log(args.category, args.content, args.source)
        print(json.dumps({"ok": True, "file": str(path)}, ensure_ascii=False))
    elif args.cmd == "query":
        print(json.dumps(query(args.keyword, args.category), ensure_ascii=False, indent=2))
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
