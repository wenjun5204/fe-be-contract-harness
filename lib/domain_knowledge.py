#!/usr/bin/env python3
"""领域知识库：可追溯、可校验、可安全更新的业务规则资产。

知识条目以带 JSON/YAML frontmatter 的 Markdown 保存。旧版纯 Markdown 仍可读取，
但不会被误认为已精确定义字段、状态或错误码。

作用域隔离(方案 B,docs/designs/kb-scope-isolation.md):目录即作用域——
    <root>/_global/<domain>/     跨项目工程约定(读侧所有 run 注入)
    <root>/products/<pid>/<domain>/  产品私有知识(仅 product_id == pid 的 run 读取)
    <root>/pending/<domain>/     product 无法解析时的 E2 回流兜底(待人工归位)
写侧 fail-closed:自动回流无 product → pending/,绝不默认落 _global/;跨产品
通用化只能经人工显式动作(confirm_entry(to_global=True) / scope="global")。
旧扁平路径 <root>/<domain>/ 无双读兼容(迁移脚本一次清零,防"忘迁移静默失效")。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
KB_DIR = REPO_ROOT / "config" / "domain-knowledge"
DOMAINS = ("business", "frontend", "backend", "qa")
ENTRY_TYPES = ("rule", "field", "lifecycle", "error-code", "permission", "ui-contract", "qa-case", "convention")
STATUSES = ("confirmed", "assumption", "deprecated")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

GLOBAL_SCOPE = "global"
PRODUCT_SCOPE = "product"
PENDING_SCOPE = "pending"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kb_dir(root: Optional[Path] = None) -> Path:
    return Path(root) if root else KB_DIR


# ---- 作用域目录解析(目录即作用域) ----

def _scope_dir(scope: str, domain: str, root: Optional[Path] = None, product: Optional[str] = None) -> Path:
    """作用域 + domain → 目录(不创建;写路径由 _entry_path 创建)。"""
    base = _kb_dir(root)
    if scope == GLOBAL_SCOPE:
        return base / "_global" / domain
    if scope == PRODUCT_SCOPE:
        pid = product or ""
        if not SLUG_RE.fullmatch(pid):
            raise ValueError(f"product 须为 1-64 位小写 slug(目录名),实际: {product!r}")
        return base / "products" / pid / domain
    if scope == PENDING_SCOPE:
        return base / "pending" / domain
    raise ValueError(f"未知作用域: {scope}(允许 global/product/pending)")


def _validate_product(product: Optional[str]) -> None:
    if product and not SLUG_RE.fullmatch(product):
        raise ValueError(f"product 须为 1-64 位小写 slug(目录名),实际: {product!r}")


def list_products(root: Optional[Path] = None) -> List[str]:
    """列出已有产品目录(孤儿检测的输入面)。"""
    base = _kb_dir(root) / "products"
    return sorted(d.name for d in base.iterdir() if d.is_dir()) if base.exists() else []


def find_orphans(root: Optional[Path] = None, known: Optional[List[str]] = None) -> List[str]:
    """products/ 下与任何已知 product_id 无对应的产品目录(作用域孤儿)。"""
    known_set = {k for k in (known or []) if k}
    return [pid for pid in list_products(root) if pid not in known_set]


def list_domains(root: Optional[Path] = None, product: Optional[str] = None) -> List[str]:
    """全局层 domain ∪ 指定产品层 domain(不创建目录)。"""
    _validate_product(product)
    names: set = set()
    for scope, pid in ((GLOBAL_SCOPE, None), (PRODUCT_SCOPE, product) if product else (None, None)):
        if scope is None:
            continue
        base = _scope_dir(scope, "business", root, pid).parent
        if base.exists():
            names.update(d.name for d in base.iterdir() if d.is_dir() and d.name in DOMAINS)
    return sorted(names)


def domain_dir(domain: str, root: Optional[Path] = None, scope: str = GLOBAL_SCOPE,
               product: Optional[str] = None) -> Path:
    """兼容旧 API 的目录获取(创建)。新代码优先用 _scope_dir。"""
    if domain not in DOMAINS:
        raise ValueError(f"未知方向: {domain},允许 {DOMAINS}")
    path = _scope_dir(scope, domain, root, product)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_entry(path: Path, scope: str) -> dict:
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
            "scope": scope,
        }
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"知识条目 frontmatter 必须为 JSON/YAML 兼容对象: {path}: {exc}") from exc
    metadata["content"] = raw[match.end():].strip()
    metadata["path"] = path
    metadata["legacy"] = False
    metadata["scope"] = scope
    metadata.setdefault("fields", [])
    metadata.setdefault("states", [])
    metadata.setdefault("error_codes", [])
    return metadata


def _scope_sources(domain: Optional[str], root: Optional[Path], product: Optional[str]) -> List[Tuple[str, Path]]:
    """(scope, 目录) 列表:global 恒在;product 指定时附产品目录(不存在则跳过)。"""
    _validate_product(product)
    domains = [domain] if domain else list_domains(root, product)
    sources: List[Tuple[str, Path]] = []
    for d in domains:
        sources.append((GLOBAL_SCOPE, _scope_dir(GLOBAL_SCOPE, d, root)))
        if product:
            sources.append((PRODUCT_SCOPE, _scope_dir(PRODUCT_SCOPE, d, root, product)))
    return sources


def load_entries(domain: Optional[str] = None, root: Optional[Path] = None, include_deprecated: bool = False,
                 product: Optional[str] = None) -> List[dict]:
    """加载 _global/<domain>/ ∪ products/<pid>/<domain>/ 的条目(带 scope 标记)。

    无 product(或产品目录尚不存在)→ 仅全局层,不报错(冷启动可用)。
    pending/ 不进读侧:那是要人工归位的悬置条目,不是可注入知识。
    """
    entries = []
    for scope, path in _scope_sources(domain, root, product):
        if not path.is_dir():
            continue
        for md in sorted(path.glob("*.md")):
            entry = _parse_entry(md, scope)
            if include_deprecated or entry.get("status") != "deprecated":
                entries.append(entry)
    return entries


def load(domain: str, root: Optional[Path] = None, product: Optional[str] = None) -> str:
    return "\n\n".join(entry["content"] for entry in load_entries(domain, root, product=product))


def load_all(root: Optional[Path] = None, product: Optional[str] = None) -> str:
    return "\n\n".join(load(domain, root, product) for domain in list_domains(root, product))


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


def _entry_path(domain: str, name: str, root: Optional[Path] = None, scope: str = GLOBAL_SCOPE,
                product: Optional[str] = None) -> Path:
    if not SLUG_RE.fullmatch(name):
        raise ValueError("name 须为 1-64 位小写 slug（字母、数字、连字符）")
    path = _scope_dir(scope, domain, root, product)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{name}.md"


def find_conflicts(candidate: dict, root: Optional[Path] = None, product: Optional[str] = None,
                   scope: Optional[str] = None) -> List[dict]:
    """检测同域、同实体已确认条目中字段/错误码定义冲突(在候选写入的同一作用域内比对)。"""
    conflicts = []
    if candidate.get("status") != "confirmed":
        return conflicts
    for existing in load_entries(candidate["domain"], root, product=product):
        if existing.get("scope") != (scope or (PRODUCT_SCOPE if product else GLOBAL_SCOPE)):
            continue
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


def write_entry(entry: dict, root: Optional[Path] = None, mode: str = "create",
                product: Optional[str] = None, scope: Optional[str] = None) -> Path:
    """安全落库：默认 create；同名条目必须显式 merge 或 replace。

    作用域(fail-closed):
    - product=<pid> → products/<pid>/<domain>/(E2 回流归位的主路径)
    - scope="global" → _global/(人工显式声明跨产品通用)
    - 其余(自动写侧 product 无法解析)→ pending/(待人工归位,绝不默认落全局)
    """
    errors = validate_entry(entry)
    if errors:
        raise ValueError("知识条目不合法: " + "; ".join(errors))
    if mode not in {"create", "merge", "replace"}:
        raise ValueError("mode 须为 create / merge / replace")
    if scope and scope not in {GLOBAL_SCOPE, PENDING_SCOPE}:
        raise ValueError(f"scope 仅接受 global/pending(产品作用域请传 product): {scope}")
    if product:
        effective_scope = PRODUCT_SCOPE
    elif scope:
        effective_scope = scope
    else:
        effective_scope = PENDING_SCOPE
    path = _entry_path(entry["domain"], entry["id"], root, effective_scope, product)
    if path.exists() and mode == "create":
        raise FileExistsError(f"知识条目已存在: {path}；请显式使用 mode=merge 或 replace")
    conflicts = find_conflicts(entry, root, product=product, scope=effective_scope)
    if conflicts and mode != "replace":
        raise ValueError(f"检测到已确认知识冲突: {json.dumps(conflicts, ensure_ascii=False)}；请人工核对后显式 replace")
    if path.exists() and mode == "merge":
        current = _parse_entry(path, effective_scope)
        if current.get("legacy"):
            raise ValueError("旧版无 Schema 条目不可自动 merge，请先迁移或显式 replace")
        if current.get("entity") != entry.get("entity"):
            raise ValueError("merge 仅允许同一 entity")
        merged = dict(current)
        merged.update({key: value for key, value in entry.items() if key not in {"fields", "states", "error_codes", "content", "path", "legacy", "scope"}})
        for key in ("fields", "states", "error_codes"):
            merged[key] = current.get(key, []) + [item for item in entry.get(key, []) if item not in current.get(key, [])]
        merged["content"] = f"{current['content'].strip()}\n\n{entry['content'].strip()}"
        entry = merged
    entry = dict(entry)
    entry["scope"] = effective_scope
    entry["updated_at"] = _now()
    path.write_text(render_entry(entry), encoding="utf-8")
    return path


def seed(domain: str, name: str, content: str, root: Optional[Path] = None,
         scope: str = GLOBAL_SCOPE) -> Path:
    """兼容旧 API；新调用应优先使用 write_entry 并提供完整元数据。"""
    return write_entry({
        "id": name, "domain": domain, "type": "rule", "status": "confirmed",
        "source": "user", "entity": name, "fields": [], "states": [], "error_codes": [],
        "content": content,
    }, root=root, mode="create", scope=scope)


def _locate_entry(domain: str, entry_id: str, root: Optional[Path] = None,
                  product: Optional[str] = None) -> Tuple[Path, str, Optional[str]]:
    """按 id 定位条目文件:指定 product → 产品目录;否则全量搜索(global/pending/products/*)。

    返回 (路径, scope, 产品目录 pid 或 None)。
    """
    _validate_product(product)
    candidates = []
    if product:
        p = _scope_dir(PRODUCT_SCOPE, domain, root, product) / f"{entry_id}.md"
        if p.is_file():
            candidates.append((p, PRODUCT_SCOPE, product))
    else:
        for scope, path in _scope_sources(domain, root, None):
            if scope == GLOBAL_SCOPE and path.is_dir():
                p = path / f"{entry_id}.md"
                if p.is_file():
                    candidates.append((p, GLOBAL_SCOPE, None))
        p = _scope_dir(PENDING_SCOPE, domain, root) / f"{entry_id}.md"
        if p.is_file():
            candidates.append((p, PENDING_SCOPE, None))
        for pid in list_products(root):
            p = _scope_dir(PRODUCT_SCOPE, domain, root, pid) / f"{entry_id}.md"
            if p.is_file():
                candidates.append((p, PRODUCT_SCOPE, pid))
    if not candidates:
        raise FileNotFoundError(f"知识条目不存在: {domain}/{entry_id}(global/pending/products 均未找到)")
    if len(candidates) > 1:
        where = ", ".join(str(p) for p, _, _ in candidates)
        raise ValueError(f"知识条目跨作用域重名,需显式指定 product: {where}")
    return candidates[0]


def confirm_entry(domain: str, entry_id: str, confirmed_by: str, root: Optional[Path] = None,
                  product: Optional[str] = None, to_global: bool = False) -> dict:
    """E3 知识确认流转:assumption → confirmed 的人工升级(带审计字段)。

    三方分工的"用户"侧落地:AI 推断写 assumption(E2 回流),人核对后经本函数
    升级为 confirmed,记录 confirmed_by/confirmed_at——知识可信层只经人工。
    fail-closed:
    - 只允许 assumption → confirmed(confirmed/deprecated 不动,防误改已定知识)
    - confirmed_by 必填(审计可追溯)
    - 与已确认知识冲突仍被 write_entry 的 find_conflicts 拦截(replace 也拦)
    - to_global=True:确认同时把条目迁至 _global/(跨产品通用是显式人工决策,
      方案 B §3.5——这是自动写侧永远到不了的路径)
    """
    path, scope, pid = _locate_entry(domain, entry_id, root, product)
    entry = _parse_entry(path, scope)
    if entry.get("legacy"):
        raise ValueError("旧版无 Schema 条目不可 confirm,请先迁移(frontmatter 化)")
    current = entry.get("status")
    if current == "confirmed":
        raise ValueError(f"条目已是 confirmed(勿重复确认): {path}")
    if current == "deprecated":
        raise ValueError(f"条目已 deprecated,不可直接 confirm(先恢复再确认): {path}")
    entry["status"] = "confirmed"
    entry["confirmed_by"] = confirmed_by
    entry["confirmed_at"] = _now()
    # 确认动作把责任转到人:source 标记确认前来源,防"AI 推断直接 confirmed"的
    # validate_entry 校验拒绝合法 confirm 流程(可追溯原始来源,又不违可信层纪律)
    original_source = entry.get("source", "unknown")
    entry["source"] = f"user_confirmed_from_{original_source}"
    # mode=replace 覆盖落盘;冲突校验对 confirmed 条目依然生效(find_conflicts 只比 confirmed)
    target_scope = GLOBAL_SCOPE if to_global and scope != GLOBAL_SCOPE else scope
    target_product = pid if target_scope == PRODUCT_SCOPE else None
    write_entry(entry, root=root, mode="replace",
                scope=None if target_product else target_scope, product=target_product)
    if target_scope != scope:
        path.unlink()  # 已在目标作用域落盘,移除旧位置(目录即作用域,不留双份)
        path = _scope_dir(target_scope, domain, root, target_product) / path.name
    return {"ok": True, "id": entry_id, "domain": domain, "status": "confirmed",
            "confirmed_by": confirmed_by, "confirmed_at": entry["confirmed_at"],
            "scope": target_scope, "file": str(path)}


def search(query: str, domain: Optional[str] = None, root: Optional[Path] = None,
           product: Optional[str] = None) -> List[dict]:
    """跨知识正文和元数据检索，返回命中的文件与行信息。"""
    hits = []
    for entry in load_entries(domain, root, include_deprecated=True, product=product):
        text = render_entry(entry)
        for line_no, line in enumerate(text.splitlines(), 1):
            if query.lower() in line.lower():
                hits.append({"domain": entry["domain"], "file": entry["path"].name, "line": line_no,
                             "text": line.strip(), "status": entry["status"], "scope": entry.get("scope")})
    return hits


def _spec_terms(spec: dict) -> List[str]:
    terms = []
    for entity in spec.get("contract_readiness", {}).get("entities", []):
        terms.append(entity.get("name", ""))
        terms.extend(field.get("name", "") for field in entity.get("fields", []))
    return [term for term in terms if term]


def coverage_report(spec: dict, domain: str = "business", root: Optional[Path] = None,
                    product: Optional[str] = None) -> dict:
    """按元数据精确计算实体、字段、状态和错误码覆盖，并报告规则冲突。"""
    entries = [entry for entry in load_entries(domain, root, product=product) if entry.get("status") == "confirmed"]
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
                missing_states.append({"entity": name, "state": str(state)})
    missing_errors = [item for item in spec.get("contract_readiness", {}).get("error_codes", []) if str(item.get("code")) not in error_defs]
    conflicts = []
    for entry in entries:
        if not entry.get("legacy"):
            conflicts.extend(find_conflicts(entry, root, product=product, scope=entry.get("scope")))
    return {
        "domain": domain,
        "missing_entity": missing_entities,
        "missing_field_definition": missing_fields,
        "missing_state_definition": missing_states,
        "missing_error_mapping": missing_errors,
        "conflicting_knowledge": conflicts,
        "legacy_entries": [entry["id"] for entry in entries if entry.get("legacy")],
    }


def identify_gaps(spec: dict, domain: str = "business", root: Optional[Path] = None,
                  product: Optional[str] = None) -> List[str]:
    """兼容旧接口，扁平返回未覆盖实体/字段名称。新代码应使用 coverage_report。"""
    report = coverage_report(spec, domain, root, product)
    return report["missing_entity"] + [item["field"] for item in report["missing_field_definition"]]


def _parse_json_arg(value: str, expected_type: type, label: str):
    parsed = json.loads(value)
    if not isinstance(parsed, expected_type):
        raise ValueError(f"{label} 必须是 JSON {expected_type.__name__}")
    return parsed


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="领域知识库(作用域隔离:目录即作用域)")
    sub = parser.add_subparsers(dest="cmd")
    search_parser = sub.add_parser("search", help="关键词检索")
    search_parser.add_argument("query")
    search_parser.add_argument("--domain", default=None)
    search_parser.add_argument("--product", default=None, help="限定产品作用域(缺省:仅全局层)")
    gaps_parser = sub.add_parser("gaps", help="输出结构化知识覆盖缺口")
    gaps_parser.add_argument("spec_file")
    gaps_parser.add_argument("--domain", default="business")
    gaps_parser.add_argument("--product", default=None)
    validate_parser = sub.add_parser("validate", help="校验知识条目 Schema")
    validate_parser.add_argument("entry_file")
    create_parser = sub.add_parser("write", help="经 Schema、冲突和写入模式校验后落库")
    create_parser.add_argument("domain")
    create_parser.add_argument("id")
    create_parser.add_argument("content")
    create_parser.add_argument("--entity", required=True)
    create_parser.add_argument("--product", default=None, help="产品作用域(E2 回流主路径)")
    create_parser.add_argument("--scope", choices=(GLOBAL_SCOPE, PENDING_SCOPE), default=None,
                               help="显式全局(人工确认跨产品通用)/pending(product 无法解析的兜底)")
    create_parser.add_argument("--type", choices=ENTRY_TYPES, default="rule")
    create_parser.add_argument("--status", choices=STATUSES, default="confirmed")
    create_parser.add_argument("--source", default="user")
    create_parser.add_argument("--fields", default="[]")
    create_parser.add_argument("--states", default="[]")
    create_parser.add_argument("--error-codes", default="[]")
    create_parser.add_argument("--mode", choices=("create", "merge", "replace"), default="create")
    confirm_parser = sub.add_parser("confirm", help="assumption → confirmed 人工确认(记录确认人)")
    confirm_parser.add_argument("domain")
    confirm_parser.add_argument("id")
    confirm_parser.add_argument("--by", required=True, help="确认人标识(审计落盘)")
    confirm_parser.add_argument("--product", default=None, help="条目所在产品作用域")
    confirm_parser.add_argument("--to-global", action="store_true",
                                help="确认同时迁移至 _global/(跨产品通用的人工显式决策)")
    sub.add_parser("domains", help="列出方向")
    sub.add_parser("scopes", help="列出作用域布局(_global/products/pending)")
    orphans_parser = sub.add_parser("orphans", help="列出与已知 product_id 无对应的产品目录")
    orphans_parser.add_argument("--known", required=True, help="已知 product_id 逗号分隔列表")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "search":
            result: Any = search(args.query, args.domain, product=args.product)
        elif args.cmd == "gaps":
            spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8"))
            result = coverage_report(spec, args.domain, product=args.product)
        elif args.cmd == "validate":
            entry = _parse_entry(Path(args.entry_file), GLOBAL_SCOPE)
            result = {"ok": not entry.get("legacy") and not validate_entry(entry), "errors": validate_entry(entry), "legacy": entry.get("legacy")}
        elif args.cmd == "write":
            entry = {
                "id": args.id, "domain": args.domain, "entity": args.entity, "type": args.type,
                "status": args.status, "source": args.source, "fields": _parse_json_arg(args.fields, list, "fields"),
                "states": _parse_json_arg(args.states, list, "states"), "error_codes": _parse_json_arg(args.error_codes, list, "error_codes"),
                "content": args.content,
            }
            result = {"ok": True, "file": str(write_entry(entry, mode=args.mode, product=args.product, scope=args.scope))}
        elif args.cmd == "domains":
            result = list_domains()
        elif args.cmd == "scopes":
            result = {"products": list_products(), "domains": list_domains(),
                      "pending": [p.name for p in sorted((KB_DIR / "pending").glob("*/*.md"))] if (KB_DIR / "pending").exists() else []}
        elif args.cmd == "orphans":
            result = {"orphans": find_orphans(known=[k for k in args.known.split(",") if k])}
        elif args.cmd == "confirm":
            result = confirm_entry(args.domain, args.id, args.by, product=args.product, to_global=args.to_global)
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
