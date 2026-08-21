#!/usr/bin/env python3
"""仓库知识提取器(工程理解冷启动)。扫描仓库 → 提取技术栈/目录/约定 → 沉淀为仓库知识。

配合 skills/build-repo-knowledge 使用;领域知识见 lib/domain_knowledge.py。
设计:确定性扫描(零依赖),CLI 供 skill/agent 通过 bash 调用。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
KB_DIR = REPO_ROOT / "config" / "repo-knowledge"

# 使 `python3 lib/repo_knowledge.py` 直接执行时也能 import lib.* 包
sys.path.insert(0, str(REPO_ROOT))

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "target", ".idea", ".vscode"}
KEY_FILES = ("package.json", "pom.xml", "build.gradle", "nest-cli.json", "vite.config.ts", "tsconfig.json", "README.md")


def detect_stack(repo_path: str) -> Dict[str, bool]:
    """用 lib/stack 的 detect 判定各技术栈是否命中。"""
    from lib.stack.adapter import get_adapter
    return {name: get_adapter(name).detect(repo_path)["detected"] for name in ("react", "vue", "node", "java")}


def scan_structure(repo_path: str, depth: int = 2) -> List[str]:
    """列出前 depth 层的目录/文件(排除依赖与产物)。"""
    repo = Path(repo_path)
    out = []
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if rel.parts and rel.parts[0] in EXCLUDE_DIRS:
            continue
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if len(rel.parts) > depth:
            continue
        out.append(str(rel))
    return out[:60]


def build_knowledge(repo_path: str) -> str:
    repo = Path(repo_path)
    name = repo.name or "root"
    stacks = detect_stack(repo_path)
    active = [s for s, on in stacks.items() if on]
    structure = scan_structure(repo_path)
    key = [f for f in KEY_FILES if (repo / f).exists()]

    lines = [f"# 仓库知识:{name}", ""]
    lines.append("## 技术栈")
    lines.append("- " + (" / ".join(active) if active else "未识别(无已知标记文件)"))
    lines.append("")
    lines.append("## 目录结构(前 2 层)")
    lines.extend(f"- {s}" for s in structure)
    lines.append("")
    lines.append("## 关键文件")
    lines.append("- " + (", ".join(key) if key else "无"))
    lines.append("")
    lines.append("## 构建/测试命令")
    if active:
        from lib.stack.adapter import get_adapter
        for s in active:
            a = get_adapter(s)
            lines.append(f"- {s}: lint={a.lint_commands()} test={a.test_commands()} coverage={a.coverage_command()}")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def save(repo_path: str, kb_dir: Optional[Path] = None) -> Path:
    kb = kb_dir or KB_DIR
    kb.mkdir(parents=True, exist_ok=True)
    name = Path(repo_path).name or "root"
    path = kb / f"{name}.md"
    path.write_text(build_knowledge(repo_path), encoding="utf-8")
    return path


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="仓库知识提取")
    p.add_argument("repo")
    p.add_argument("--out", default=None, help="输出知识目录,默认 config/repo-knowledge")
    args = p.parse_args(argv)
    kb = Path(args.out) if args.out else None
    path = save(args.repo, kb)
    print(json.dumps({"ok": True, "file": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
