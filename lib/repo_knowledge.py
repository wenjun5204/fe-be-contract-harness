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


def scaffold(repo_path: str, project_name: Optional[str] = None) -> dict:
    """生成 .agents/ 知识库骨架 + 复制注入脚本(确定性部分;内容由 LLM 填充)。"""
    repo = Path(repo_path)
    project_name = project_name or repo.name
    docs = repo / ".agents" / "docs"
    scripts = repo / ".agents" / "scripts"
    test_examples = repo / ".agents" / "test-examples"
    for d in (docs / "services", scripts, test_examples / "baseline", test_examples / "delivery"):
        d.mkdir(parents=True, exist_ok=True)

    template_dir = REPO_ROOT / "skills" / "build-repo-knowledge" / "script-templates"
    created = []
    for tpl in sorted(template_dir.glob("*.sh")):
        content = tpl.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", project_name)
        dest = scripts / tpl.name
        dest.write_text(content, encoding="utf-8")
        dest.chmod(0o755)
        created.append(str(dest.relative_to(repo)))

    for rel in ("AGENTS.md", ".agents/docs/architecture.md", ".agents/docs/conventions.md", ".agents/docs/domain-model.md"):
        p = repo / rel
        if not p.exists():
            p.write_text(f"<!-- {rel} 待 build-repo-knowledge 生成 -->\n", encoding="utf-8")
            created.append(rel)

    return {"repo": str(repo), "created": created}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="仓库知识提取")
    sub = p.add_subparsers(dest="cmd")

    b = sub.add_parser("build", help="生成单文件仓库知识(技术栈/结构/命令)")
    b.add_argument("repo")
    b.add_argument("--out", default=None)

    s = sub.add_parser("scaffold", help="生成 .agents/ 知识库骨架 + 注入脚本")
    s.add_argument("repo")
    s.add_argument("--name", default=None)

    args = p.parse_args(argv)
    if args.cmd == "build":
        kb = Path(args.out) if args.out else None
        path = save(args.repo, kb)
        print(json.dumps({"ok": True, "file": str(path)}, ensure_ascii=False))
    elif args.cmd == "scaffold":
        print(json.dumps(scaffold(args.repo, args.name), ensure_ascii=False, indent=2))
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
