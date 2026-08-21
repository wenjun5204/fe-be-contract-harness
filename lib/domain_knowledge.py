#!/usr/bin/env python3
"""业务领域知识库(SDD 冷启动 + 知识更新)。按 业务/前端/后端/QA 四方向沉淀领域知识。

职责:
1. list_domains / load —— 列出/加载某方向知识
2. search —— 关键词检索(跨方向)
3. seed —— 冷启动写入新知识(沉淀澄清结论)
4. identify_gaps —— 对比结构化 Spec 与知识库,识别"知识库未覆盖"的实体/字段(即需求模糊点)

设计:markdown 文件即知识单元,零依赖;CLI 供 agent 通过 bash 调用。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
KB_DIR = REPO_ROOT / "config" / "domain-knowledge"
DOMAINS = ("business", "frontend", "backend", "qa")


def _kb_dir(root: Optional[Path] = None) -> Path:
    return Path(root) if root else KB_DIR


def list_domains(root: Optional[Path] = None) -> List[str]:
    return sorted(d.name for d in _kb_dir(root).iterdir() if d.is_dir())


def domain_dir(domain: str, root: Optional[Path] = None) -> Path:
    d = _kb_dir(root) / domain
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(domain: str, root: Optional[Path] = None) -> str:
    """合并某方向所有知识文件。"""
    parts = []
    for f in sorted(domain_dir(domain, root).glob("*.md")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def load_all(root: Optional[Path] = None) -> str:
    return "\n\n".join(load(d, root) for d in list_domains(root))


def search(query: str, domain: Optional[str] = None, root: Optional[Path] = None) -> List[dict]:
    """关键词检索,返回 [{domain, file, line, text}]。"""
    hits = []
    domains = [domain] if domain else list_domains(root)
    for d in domains:
        for f in sorted(domain_dir(d, root).glob("*.md")):
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if query.lower() in line.lower():
                    hits.append({"domain": d, "file": f.name, "line": i, "text": line.strip()})
    return hits


def seed(domain: str, name: str, content: str, root: Optional[Path] = None) -> Path:
    """冷启动:写入一条新知识(把澄清结论沉淀下来)。"""
    if domain not in DOMAINS:
        raise ValueError(f"未知方向: {domain},允许 {DOMAINS}")
    path = domain_dir(domain, root) / f"{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


def _spec_terms(spec: dict) -> List[str]:
    """从结构化 Spec 提取实体名 + 字段名(作为"该知道的术语")。"""
    terms = []
    for e in spec.get("contract_readiness", {}).get("entities", []):
        terms.append(e.get("name", ""))
        for f in e.get("fields", []):
            terms.append(f.get("name", ""))
    return [t for t in terms if t]


def identify_gaps(spec: dict, domain: str = "business", root: Optional[Path] = None) -> List[str]:
    """识别知识库未覆盖的实体/字段 = 需求模糊点(需澄清或沉淀新知识)。"""
    kb = load(domain, root).lower()
    return [t for t in _spec_terms(spec) if t and t.lower() not in kb]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="领域知识库")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("search", help="关键词检索")
    s.add_argument("query")
    s.add_argument("--domain", default=None)

    g = sub.add_parser("gaps", help="识别 Spec 的知识模糊点")
    g.add_argument("spec_file")
    g.add_argument("--domain", default="business")

    sd = sub.add_parser("seed", help="冷启动写入知识")
    sd.add_argument("domain")
    sd.add_argument("name")
    sd.add_argument("content")

    sub.add_parser("domains", help="列出方向")

    args = p.parse_args(argv)

    if args.cmd == "search":
        print(json.dumps(search(args.query, args.domain), ensure_ascii=False, indent=2))
    elif args.cmd == "gaps":
        spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8"))
        print(json.dumps(identify_gaps(spec, args.domain), ensure_ascii=False))
    elif args.cmd == "seed":
        path = seed(args.domain, args.name, args.content)
        print(json.dumps({"ok": True, "file": str(path)}, ensure_ascii=False))
    elif args.cmd == "domains":
        print(json.dumps(list_domains(), ensure_ascii=False))
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
