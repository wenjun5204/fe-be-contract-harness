#!/usr/bin/env python3
"""仓库知识提取器：安全初始化、确定性扫描与知识库完整性校验。"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
KB_DIR = REPO_ROOT / "config" / "repo-knowledge"
sys.path.insert(0, str(REPO_ROOT))

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "target", ".idea", ".vscode"}
KEY_FILES = ("package.json", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "requirements.txt", "pyproject.toml", "nest-cli.json", "vite.config.ts", "tsconfig.json", "README.md")
REQUIRED_DOCS = ("AGENTS.md", ".agents/docs/architecture.md", ".agents/docs/conventions.md", ".agents/docs/domain-model.md")
PLACEHOLDER = "待 build-repo-knowledge 生成"


def detect_stack(repo_path: str) -> Dict[str, bool]:
    """识别 Harness 深度支持的 React/Vue/Node/Java 技术栈。"""
    from lib.stack.adapter import get_adapter
    return {name: get_adapter(name).detect(repo_path)["detected"] for name in ("react", "vue", "node", "java")}


def validate_repo(repo_path: str | Path, require_git: bool = True) -> dict:
    """校验路径、Git、读写权限与依赖文件；无依赖文件仅作为降级警告。"""
    repo = Path(repo_path).expanduser().resolve()
    errors, warnings = [], []
    if not repo.exists():
        errors.append(f"路径不存在: {repo}")
    elif not repo.is_dir():
        errors.append(f"不是目录: {repo}")
    else:
        if require_git and not (repo / ".git").exists():
            errors.append(f"不是 Git 仓库（缺少 .git）: {repo}")
        if not os.access(repo, os.R_OK):
            errors.append(f"目录不可读: {repo}")
        if not os.access(repo, os.W_OK):
            errors.append(f"目录不可写: {repo}")
    dependency_files = [name for name in KEY_FILES if repo.exists() and (repo / name).exists()]
    if repo.exists() and repo.is_dir() and not dependency_files:
        warnings.append("未发现已知依赖文件；将仅生成低置信度的目录结构知识")
    stacks = detect_stack(str(repo)) if not errors else {}
    return {"ok": not errors, "repo": str(repo), "errors": errors, "warnings": warnings, "dependency_files": dependency_files, "detected_stacks": stacks}


def scan_structure(repo_path: str, depth: int = 2) -> List[str]:
    repo = Path(repo_path)
    out = []
    for path in sorted(repo.rglob("*")):
        rel = path.relative_to(repo)
        if any(part in EXCLUDE_DIRS for part in rel.parts) or len(rel.parts) > depth:
            continue
        out.append(str(rel))
    return out[:60]


def build_knowledge(repo_path: str) -> str:
    validation = validate_repo(repo_path)
    if not validation["ok"]:
        raise ValueError("仓库校验失败: " + "; ".join(validation["errors"]))
    repo = Path(validation["repo"])
    active = [name for name, detected in validation["detected_stacks"].items() if detected]
    lines = [f"# 仓库知识:{repo.name or 'root'}", "", "## 扫描置信度"]
    lines.append("- 低：未发现依赖文件，仅基于目录结构" if validation["warnings"] else "- 中：基于依赖文件、技术栈与目录结构的确定性扫描")
    lines.extend(["", "## 技术栈", "- " + (" / ".join(active) if active else "未识别（当前仅深度支持 React/Vue/Node/Java）"), "", "## 目录结构（前 2 层)"])
    lines.extend(f"- {item}" for item in scan_structure(str(repo)))
    lines.extend(["", "## 关键文件", "- " + (", ".join(validation["dependency_files"]) if validation["dependency_files"] else "无"), "", "## 构建/测试命令"])
    if active:
        from lib.stack.adapter import get_adapter
        for stack in active:
            adapter = get_adapter(stack)
            lines.append(f"- {stack}: lint={adapter.lint_commands()} test={adapter.test_commands()} coverage={adapter.coverage_command()}")
    else:
        lines.append("- 未识别；需要人工补充")
    return "\n".join(lines) + "\n"


def save(repo_path: str, kb_dir: Optional[Path] = None) -> Path:
    kb = kb_dir or KB_DIR
    kb.mkdir(parents=True, exist_ok=True)
    path = kb / f"{Path(repo_path).resolve().name or 'root'}.md"
    path.write_text(build_knowledge(repo_path), encoding="utf-8")
    return path


def _write_file(path: Path, content: str, mode: str, created: List[str], skipped: List[str], replaced: List[str], repo: Path, executable: bool = False) -> None:
    if path.exists():
        if mode == "create":
            skipped.append(str(path.relative_to(repo)))
            return
        if mode == "merge":
            skipped.append(str(path.relative_to(repo)))
            return
        replaced.append(str(path.relative_to(repo)))
    else:
        created.append(str(path.relative_to(repo)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def scaffold(repo_path: str, project_name: Optional[str] = None, mode: str = "create") -> dict:
    """安全初始化知识库；create/merge 不覆盖，replace 才覆盖既有文件。"""
    if mode not in {"create", "merge", "replace"}:
        raise ValueError("mode 须为 create / merge / replace")
    validation = validate_repo(repo_path)
    if not validation["ok"]:
        raise ValueError("仓库校验失败: " + "; ".join(validation["errors"]))
    repo = Path(validation["repo"])
    project_name = project_name or repo.name
    scripts = repo / ".agents" / "scripts"
    for directory in (repo / ".agents" / "docs" / "services", scripts, repo / ".agents" / "test-examples" / "baseline", repo / ".agents" / "test-examples" / "delivery", repo / ".agents" / "plans"):
        directory.mkdir(parents=True, exist_ok=True)
    created, skipped, replaced = [], [], []
    template_dir = REPO_ROOT / "skills" / "build-repo-knowledge" / "script-templates"
    for template in sorted(template_dir.glob("*.sh")):
        _write_file(scripts / template.name, template.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", project_name), mode, created, skipped, replaced, repo, executable=True)
    for rel in REQUIRED_DOCS:
        _write_file(repo / rel, f"<!-- {rel} {PLACEHOLDER} -->\n", mode, created, skipped, replaced, repo)
    return {"repo": str(repo), "mode": mode, "created": created, "skipped": skipped, "replaced": replaced, "warnings": validation["warnings"]}


def validate_knowledge(repo_path: str | Path) -> dict:
    """验证知识库核心文档是否存在、是否仍为占位符，以及服务文档是否可发现。"""
    repo = Path(repo_path).expanduser().resolve()
    missing, placeholders = [], []
    for rel in REQUIRED_DOCS:
        path = repo / rel
        if not path.exists():
            missing.append(rel)
        elif PLACEHOLDER in path.read_text(encoding="utf-8"):
            placeholders.append(rel)
    services = sorted(str(path.relative_to(repo)) for path in (repo / ".agents" / "docs" / "services").glob("*.md"))
    return {"ok": not missing and not placeholders, "repo": str(repo), "missing": missing, "placeholders": placeholders, "services": services, "next_actions": (["填充缺失或仍含占位符的核心文档"] if missing or placeholders else [])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="仓库知识提取")
    sub = parser.add_subparsers(dest="cmd")
    validate = sub.add_parser("validate-repo", help="校验目标仓库是否适合构建知识库")
    validate.add_argument("repo")
    build = sub.add_parser("build", help="生成单文件确定性仓库扫描结果")
    build.add_argument("repo")
    build.add_argument("--out", default=None)
    scaffold_parser = sub.add_parser("scaffold", help="安全创建知识库骨架与注入脚本")
    scaffold_parser.add_argument("repo")
    scaffold_parser.add_argument("--name", default=None)
    scaffold_parser.add_argument("--mode", choices=("create", "merge", "replace"), default="create")
    knowledge = sub.add_parser("validate-knowledge", help="检查知识库文档完整性和占位符")
    knowledge.add_argument("repo")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.cmd == "validate-repo":
            result = validate_repo(args.repo)
        elif args.cmd == "build":
            result = {"ok": True, "file": str(save(args.repo, Path(args.out) if args.out else None))}
        elif args.cmd == "scaffold":
            result = scaffold(args.repo, args.name, args.mode)
        elif args.cmd == "validate-knowledge":
            result = validate_knowledge(args.repo)
        else:
            parser.print_help()
            return 1
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    sys.exit(main())
