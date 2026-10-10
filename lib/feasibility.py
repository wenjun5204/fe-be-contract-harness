#!/usr/bin/env python3
"""可行性验证(SDD):检索线上代码,判断需求设计的实体/字段是否可落地、是否冲突。

职责:对结构化 Spec 的实体,在目标仓库中检索已有定义,产出可行性报告。
- new:仓库无同名 → 新实体,可落地
- existing:仓库已有同名 → 需人工确认「复用 vs 冲突」

设计:纯文件检索(零依赖),CLI 供 agent 通过 bash 调用。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "target"}
EXCLUDE_SUFFIXES = {".lock", ".pyc", ".map", ".min.js", ".sum"}


def _walk_files(repo: Path):
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.suffix in EXCLUDE_SUFFIXES:
            continue
        yield p


def _search_repo(repo: Path, term: str, limit: int = 3) -> List[str]:
    hits = []
    for f in _walk_files(repo):
        try:
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                if term in line:
                    hits.append(f"{f.relative_to(repo)}:{line.strip()[:90]}")
                    if len(hits) >= limit:
                        return hits
        except OSError:
            continue
    return hits


def check_feasibility(spec: dict, repo_path: str) -> dict:
    """返回 {ok, repo, findings, summary}。

    ok=False 仅当存在同名实体(需人工确认复用/冲突),不阻断,只提示。
    """
    repo = Path(repo_path)
    findings: List[dict] = []
    existing = 0
    new = 0
    for e in spec.get("contract_readiness", {}).get("entities", []):
        name = e.get("name", "")
        if not name:
            continue
        matches = _search_repo(repo, name)
        if matches:
            existing += 1
            findings.append({
                "entity": name,
                "status": "existing",
                "matches": matches,
                "note": "同名已存在,需确认复用还是冲突",
            })
        else:
            new += 1
            findings.append({"entity": name, "status": "new", "matches": [], "note": "新实体,可落地"})
    return {
        "ok": existing == 0,
        "repo": str(repo),
        "findings": findings,
        "summary": {"new": new, "existing": existing},
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="可行性验证")
    p.add_argument("spec_file")
    p.add_argument("repo")
    args = p.parse_args(argv)
    spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8"))
    print(json.dumps(check_feasibility(spec, args.repo), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
