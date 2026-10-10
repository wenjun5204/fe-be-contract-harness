#!/usr/bin/env python3
"""领域知识库：可追溯、可校验、可安全更新的业务规则资产。

知识条目以带 JSON/YAML frontmatter 的 Markdown 保存。旧版纯 Markdown 仍可读取，
但不会被误认为已精确定义字段、状态或错误码。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
KB_DIR = REPO_ROOT / "config" / "domain-knowledge"
DOMAINS = ("business", "frontend", "backend", "qa")
ENTRY_TYPES = ("rule", "field", "lifecycle", "error-code", "permission", "ui-contract", "qa-case", "convention")
STATUSES = ("confirmed", "assumption", "deprecated")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kb_dir(root: Optional[Path] = None) -> Path:
    return Path(root) if root else KB_DIR


def list_domains(root: Optional[Path] = None) -> List[str]:
    base = _kb_dir(root)
    return sorted(d.name for d in base.iterdir() if d.is_dir()) if base.exists() else []


def domain_dir(domain: str, root: Optional[Path] = None) -> Path:
    if domain not in DOMAINS:
        raise ValueError(f"未知方向: {domain},允许 {DOMAINS}")
    path = _kb_dir(root) / domain
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_entry(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        # 兼容已有人工维护的旧文件；只允许其参与全文检索，不产生精确覆盖结论。
        return {
            "id": path.stem,
            "domain": path.parent.name,
            "type": "legacy",
            "status": "confirmed",
            "source": "legacy",
            "entity": None,
            "fields": [],
            "states": [],
            "error_codes": [],
            "content": raw.strip(),
            "path": path,
            "legacy": True,
        }
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"知识条目 frontmatter 必须为 JSON/YAML 兼容对象: {path}: {exc}") from exc
    metadata["content"] = raw[match.end():].strip()
    metadata["path"] = path
    metadata["legacy"] = False
    metadata.setdefault("fields", [])
    metadata.setdefault("states", [])
    metadata.setdefault("error_codes", [])
    return metadata


def load_entries(domain: Optional[str] = None, root: Optional[Path] = None, include_deprecated: bool = False) -> List[dict]:
    domains = [domain] if domain else list_domains(root)
    entries = []
    for item_domain in domains:
        for path in sorted(domain_dir(item_domain, root).glob("*.md")):
            entry = _parse_entry(path)
            if include_deprecated or entry.get("status") != "deprecated":
                entries.append(entry)
    return entries


def load(domain: str, root: Optional[Path] = None) -> str:
    return "\n\n".join(entry["content"] for entry in load_entries(domain, root))


def load_all(root: Optional[Path] = None) -> str:
    return "\n\n".join(load(domain, root) for domain in list_domains(root))


def validate_entry(entry: dict) -> List[str]:
    """返回条目 Schema 问题；空列表表示条目可安全参与领域判断。"""
    errors = []
    for field in ("id", "domain", "type", "status", "source", "entity"):
        if not entry.get(field):
            errors.append(f"缺少必填字段: {field}")
    if entry.get("id") and not SLUG_RE.fullmatch(str(entry["id"])):
        errors.append("id 须为 1-64 位小写 slug（字母、数字、连字符）")
    if entry.get("domain") not in DOMAINS:
        errors.append(f"domain 须为 {DOMAINS}")
    if entry.get("type") not in ENTRY_TYPES:
        errors.append(f"type 须为 {ENTRY_TYPES}")
    if entry.get("status") not in STATUSES:
        errors.append(f"status 须为 {STATUSES}")
    if entry.get("status") == "confirmed" and entry.get("source") in {"ai_inference", ""}:
        errors.append("AI 推断不能直接写入 confirmed；请先人工确认或使用 assumption")
    if not entry.get("content", "").strip():
        errors.append("知识正文不能为空")
    for collection in ("fields", "states", "error_codes"):
        if not isinstance(entry.get(collection, []), list):
            errors.append(f"{collection} 必须为列表")
    for field in entry.get("fields", []):
        if not isinstance(field, dict) or not field.get("name"):
            errors.append("fields 每项须包含 name")
    return errors


def render_entry(entry: dict) -> str:
    metadata = {key: value for key, value in entry.items() if key not in {"content", "path", "legacy"}}
    return f"---\n{json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)}\n---\n\n{entry['content'].strip()}\n"


def _entry_path(domain: str, name: str, root: Optional[Path] = None) -> Path:
    if not SLUG_RE.fullmatch(name):
        raise ValueError("name 须为 1-64 位小写 slug（字母、数字、连字符）")
    return domain_dir(domain, root) / f"{name}.md"


def find_conflicts(candidate: dict, root: Optional[Path] = None) -> List[dict]:
    """检测同域、同实体已确认条目中字段/错误码定义冲突。"""
    conflicts = []
    if candidate.get("status") != "confirmed":
        return conflicts
    for existing in load_entries(candidate["domain"], root):
        if existing.get("legacy") or existing.get("status") != "confirmed":
            continue
        if existing.get("id") == candidate.get("id") or existing.get("entity") != candidate.get("entity"):
            continue
        old_fields = {item["name"]: item for item in existing.get("fields", []) if item.get("name")}
        for field in candidate.get("fields", []):
            old = old_fields.get(field.get("name"))
            if old and old != field:
                conflicts.append({"kind": "field", "entity": candidate["entity"], "name": field["name"], "existing": existing["id"]})
        old_errors = {str(item.get("code")): item for item in existing.get("error_codes", []) if item.get("code") is not None}
        for error in candidate.get("error_codes", []):
            old = old_errors.get(str(error.get("code")))
            if old and old != error:
                conflicts.append({"kind": "error_code", "entity": candidate["entity"], "name": str(error["code"]), "existing": existing["id"]})
    return conflicts


def write_entry(entry: dict, root: Optional[Path] = None, mode: str = "create") -> Path:
    """安全落库：默认 create；同名条目必须显式 merge 或 replace。"""
    errors = validate_entry(entry)
    if errors:
        raise ValueError("知识条目不合法: " + "; ".join(errors))
    if mode not in {"create", "merge", "replace"}:
        raise ValueError("mode 须为 create / merge / replace")
    path = _entry_path(entry["domain"], entry["id"], root)
    if path.exists() and mode == "create":
        raise FileExistsError(f"知识条目已存在: {path}；请显式使用 mode=merge 或 replace")
    conflicts = find_conflicts(entry, root)
    if conflicts and mode != "replace":
        raise ValueError(f"检测到已确认知识冲突: {json.dumps(conflicts, ensure_ascii=False)}；请人工核对后显式 replace")
    if path.exists() and mode == "merge":
        current = _parse_entry(path)
        if current.get("legacy"):
            raise ValueError("旧版无 Schema 条目不可自动 merge，请先迁移或显式 replace")
        if current.get("entity") != entry.get("entity"):
            raise ValueError("merge 仅允许同一 entity")
        merged = dict(current)
        merged.update({key: value for key, value in entry.items() if key not in {"fields", "states", "error_codes", "content", "path", "legacy"}})
        for key in ("fields", "states", "error_codes"):
            merged[key] = current.get(key, []) + [item for item in entry.get(key, []) if item not in current.get(key, [])]
        merged["content"] = f"{current['content'].strip()}\n\n{entry['content'].strip()}"
        entry = merged
    entry = dict(entry)
    entry["updated_at"] = _now()
    path.write_text(render_entry(entry), encoding="utf-8")
    return path


def seed(domain: str, name: str, content: str, root: Optional[Path] = None) -> Path:
    """兼容旧 API；新调用应优先使用 write_entry 并提供完整元数据。"""
    return write_entry({
        "id": name, "domain": domain, "type": "rule", "status": "confirmed",
        "source": "user", "entity": name, "fields": [], "states": [], "error_codes": [],
        "content": content,
    }, root=root, mode="create")


def search(query: str, domain: Optional[str] = None, root: Optional[Path] = None) -> List[dict]:
    """跨知识正文和元数据检索，返回命中的文件与行信息。"""
    hits = []
    for entry in load_entries(domain, root, include_deprecated=True):
        text = render_entry(entry)
        for line_no, line in enumerate(text.splitlines(), 1):
            if query.lower() in line.lower():
                hits.append({"domain": entry["domain"], "file": entry["path"].name, "line": line_no, "text": line.strip(), "status": entry["status"]})
    return hits


def _spec_terms(spec: dict) -> List[str]:
    terms = []
    for entity in spec.get("contract_readiness", {}).get("entities", []):
        terms.append(entity.get("name", ""))
        terms.extend(field.get("name", "") for field in entity.get("fields", []))
    return [term for term in terms if term]


def coverage_report(spec: dict, domain: str = "business", root: Optional[Path] = None) -> dict:
    """按元数据精确计算实体、字段、状态和错误码覆盖，并报告规则冲突。"""
    entries = [entry for entry in load_entries(domain, root) if entry.get("status") == "confirmed"]
    entities = {str(entry.get("entity", "")).lower() for entry in entries if not entry.get("legacy")}
    field_defs: Dict[str, set] = {}
    state_defs: Dict[str, set] = {}
    error_defs = set()
    for entry in entries:
        if entry.get("legacy"):
            continue
        entity = str(entry.get("entity", "")).lower()
        field_defs.setdefault(entity, set()).update(str(field["name"]).lower() for field in entry.get("fields", []) if field.get("name"))
        state_defs.setdefault(entity, set()).update(str(state).lower() for state in entry.get("states", []))
        error_defs.update(str(error["code"]) for error in entry.get("error_codes", []) if error.get("code") is not None)

    missing_entities, missing_fields, missing_states = [], [], []
    for entity in spec.get("contract_readiness", {}).get("entities", []):
        name = entity.get("name", "")
        key = name.lower()
        if key not in entities:
            missing_entities.append(name)
        for field in entity.get("fields", []):
            if field.get("name") and field["name"].lower() not in field_defs.get(key, set()):
                missing_fields.append({"entity": name, "field": field["name"]})
        for state in entity.get("states", []):
            if str(state).lower() not in state_defs.get(key, set()):
                missing_states.append({"entity": name, "state": state})
    missing_errors = [item for item in spec.get("contract_readiness", {}).get("error_codes", []) if str(item.get("code")) not in error_defs]
    conflicts = []
    for entry in entries:
        if not entry.get("legacy"):
            conflicts.extend(find_conflicts(entry, root))
    return {
        "domain": domain,
        "missing_entity": missing_entities,
        "missing_field_definition": missing_fields,
        "missing_state_definition": missing_states,
        "missing_error_mapping": missing_errors,
        "conflicting_knowledge": conflicts,
        "legacy_entries": [entry["id"] for entry in entries if entry.get("legacy")],
    }


def identify_gaps(spec: dict, domain: str = "business", root: Optional[Path] = None) -> List[str]:
    """兼容旧接口，扁平返回未覆盖实体/字段名称。新代码应使用 coverage_report。"""
    report = coverage_report(spec, domain, root)
    return report["missing_entity"] + [item["field"] for item in report["missing_field_definition"]]


def _parse_json_arg(value: str, expected_type: type, label: str):
    parsed = json.loads(value)
    if not isinstance(parsed, expected_type):
        raise ValueError(f"{label} 必须是 JSON {expected_type.__name__}")
    return parsed


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="领域知识库")
    sub = parser.add_subparsers(dest="cmd")
    search_parser = sub.add_parser("search", help="关键词检索")
    search_parser.add_argument("query")
    search_parser.add_argument("--domain", default=None)
    gaps_parser = sub.add_parser("gaps", help="输出结构化知识覆盖缺口")
    gaps_parser.add_argument("spec_file")
    gaps_parser.add_argument("--domain", default="business")
    validate_parser = sub.add_parser("validate", help="校验知识条目 Schema")
    validate_parser.add_argument("entry_file")
    create_parser = sub.add_parser("write", help="经 Schema、冲突和写入模式校验后落库")
    create_parser.add_argument("domain")
    create_parser.add_argument("id")
    create_parser.add_argument("content")
    create_parser.add_argument("--entity", required=True)
    create_parser.add_argument("--type", choices=ENTRY_TYPES, default="rule")
    create_parser.add_argument("--status", choices=STATUSES, default="confirmed")
    create_parser.add_argument("--source", default="user")
    create_parser.add_argument("--fields", default="[]")
    create_parser.add_argument("--states", default="[]")
    create_parser.add_argument("--error-codes", default="[]")
    create_parser.add_argument("--mode", choices=("create", "merge", "replace"), default="create")
    sub.add_parser("domains", help="列出方向")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "search":
            result: Any = search(args.query, args.domain)
        elif args.cmd == "gaps":
            spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8"))
            result = coverage_report(spec, args.domain)
        elif args.cmd == "validate":
            entry = _parse_entry(Path(args.entry_file))
            result = {"ok": not entry.get("legacy") and not validate_entry(entry), "errors": validate_entry(entry), "legacy": entry.get("legacy")}
        elif args.cmd == "write":
            entry = {
                "id": args.id, "domain": args.domain, "entity": args.entity, "type": args.type,
                "status": args.status, "source": args.source, "fields": _parse_json_arg(args.fields, list, "fields"),
                "states": _parse_json_arg(args.states, list, "states"), "error_codes": _parse_json_arg(args.error_codes, list, "error_codes"),
                "content": args.content,
            }
            result = {"ok": True, "file": str(write_entry(entry, mode=args.mode))}
        elif args.cmd == "domains":
            result = list_domains()
        else:
            parser.print_help()
            return 1
    except (OSError, ValueError, FileExistsError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
