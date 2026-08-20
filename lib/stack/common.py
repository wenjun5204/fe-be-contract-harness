#!/usr/bin/env python3
"""TS 类型映射与代码生成公共助手。

React 前端与 Node(Nest)后端均为 TypeScript,共享同一套 OpenAPI→TS 类型映射;
Vue 前端也走 TS(后续 M2),Java 后端需独立映射(见 M2)。
"""
from __future__ import annotations

import json
import re
from typing import Dict, Set


def ref_name(schema: dict) -> str:
    ref = schema.get("$ref")
    return ref.rsplit("/", 1)[-1] if ref else ""


def ts_type(schema: dict, schemas: Dict[str, dict], depth: int = 0) -> str:
    """OpenAPI schema → TypeScript 类型字符串(支持 $ref/array/object/enum/基础类型)。"""
    if not schema:
        return "void"
    if "$ref" in schema:
        return ref_name(schema)
    if "enum" in schema:
        return " | ".join(json.dumps(v, ensure_ascii=False) for v in schema["enum"])
    t = schema.get("type")
    if t == "string":
        return "string"
    if t in ("integer", "number"):
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "array":
        items = schema.get("items", {})
        return f"{ts_type(items, schemas, depth + 1)}[]"
    if t == "object":
        props = schema.get("properties", {})
        if props:
            required = set(schema.get("required", []))
            fields = [
                f"{p}{'' if p in required else '?'}: {ts_type(ps, schemas, depth + 1)}"
                for p, ps in props.items()
            ]
            return "{ " + "; ".join(fields) + " }"
        return "Record<string, unknown>"
    return "unknown"


def _fields(schema: dict, schemas: Dict[str, dict]) -> list:
    """返回 [(field_name, ts_type_str, required?)]。"""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    return [
        (p, ts_type(ps, schemas), p in required)
        for p, ps in props.items()
    ]


def ts_interface(name: str, schema: dict, schemas: Dict[str, dict]) -> str:
    lines = [f"export interface {name} {{"]
    for p, t, req in _fields(schema, schemas):
        lines.append(f"  {p}{'' if req else '?'}: {t};")
    lines.append("}")
    return "\n".join(lines)


def ts_class(name: str, schema: dict, schemas: Dict[str, dict]) -> str:
    lines = [f"// 自动生成 DTO:{name}(勿手改)", f"export class {name} {{"]
    for p, t, req in _fields(schema, schemas):
        lines.append(f"  {p}{'' if req else '?'}: {t};")
    lines.append("}")
    return "\n".join(lines)


def collect_refs(schema, acc: Set[str] = None) -> Set[str]:
    """递归收集 schema 中引用的所有命名类型名。"""
    if acc is None:
        acc = set()
    if isinstance(schema, dict):
        if "$ref" in schema:
            acc.add(ref_name(schema))
        for v in schema.values():
            collect_refs(v, acc)
    elif isinstance(schema, list):
        for v in schema:
            collect_refs(v, acc)
    return acc


def nest_route(path: str) -> str:
    """OpenAPI 路径 → Nest 路由:/pets/{petId} → /:petId"""
    return re.sub(r"\{([^}]+)\}", r":\1", path)
