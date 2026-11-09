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


# 平台路径前缀段(版本/网关形态,非业务资源):/v1/*、/api/* 等
_PLATFORM_PATH_PREFIX = re.compile(r"(?i)^(v\d+(?:\.\d+)*|api|apis|rest|openapi)$")


def resource_groups(endpoints: list) -> Dict[str, list]:
    """端点按资源分组(版本前缀感知)。返回 {base 路径: 端点列表}。

    真实首跑发现(Stripe 612 端点):全量 /v1/* 按首段分组会退化成单个巨型
    V1Controller(612 方法/3237 行)。分组键改为"含平台前缀的资源 base 路径"
    ——扫描路径段,跳过版本前缀段(v1/api 等)与参数段({id}),首个业务段
    及其之前的前缀构成 base:
    - /pets、/pets/{id} → "/pets"(小契约行为不变)
    - /v1/charges、/v1/charges/{id} → "/v1/charges"
    - /{user}/orders → "/{user}/orders"
    """
    groups: Dict[str, list] = {}
    for ep in endpoints:
        segs = [s for s in ep["path"].strip("/").split("/") if s]
        idx = 0
        for i, s in enumerate(segs):
            if not _PLATFORM_PATH_PREFIX.match(s) and "{" not in s:
                idx = i
                break
        base = "/" + "/".join(segs[: idx + 1])
        groups.setdefault(base, []).append(ep)
    return groups


def resource_name(base_path: str) -> str:
    """base 路径 → 资源名(最后一段;全前缀路径如实返回该段)。"""
    segs = [s for s in base_path.strip("/").split("/") if s]
    return segs[-1] if segs else "root"


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
