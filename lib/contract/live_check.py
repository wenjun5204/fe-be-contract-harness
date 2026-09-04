#!/usr/bin/env python3
"""运行时契约校验(live check)—— 补 drift 检测的骨架盲区。

背景:drift_check 只比对「重新生成的骨架 manifest」,真实业务代码是手写的,
序列化框架改名的字段(例:Jackson 把 isMine() 序列化为 mine)只有运行时才暴露。
本模块拉取运行中服务导出的 OpenAPI 文档(如 springdoc 的 /v3/api-docs),
与 SSOT 契约逐项比对:

1. 路由(method+path)缺失/多余
2. operationId 不一致
3. schema 字段缺失/多余(序列化漂移的直接证据)
4. required 不一致
5. 枚举值漂移

纯函数比对核心 + 网络拉取分离,便于单测。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen

from lib.contract.parser import HTTP_METHODS, parse_contract


def fetch_live_doc(url: str, timeout: float = 10.0) -> dict:
    """拉取运行时 OpenAPI JSON 文档。"""
    with urlopen(url, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict) or "paths" not in data:
        raise ValueError(f"响应不是 OpenAPI 文档(缺少 paths): {url}")
    return data


def _live_endpoints(live: dict) -> Dict[Tuple[str, str], str]:
    """(method, path) -> operationId。operationId 缺失时生成占位(用于路由级比对)。"""
    out: Dict[Tuple[str, str], str] = {}
    for path, item in (live.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            op = item.get(method)
            if not op:
                continue
            out[(method.upper(), path)] = op.get("operationId") or ""
    return out


def _match_live_schema_name(live_schemas: Dict[str, dict], contract_name: str) -> Optional[str]:
    """按契约模型名找运行时 schema:支持嵌套类命名(Outer.Inner / Outer$Inner)。

    springdoc 对 Java 嵌套静态类的命名通常是 Outer.Inner,契约模型名通常取 Inner。
    """
    if contract_name in live_schemas:
        return contract_name
    for live_name in live_schemas:
        if live_name.endswith("." + contract_name) or live_name.endswith("$" + contract_name):
            return live_name
    return None


def _inline_enums(live: dict) -> List[List[str]]:
    """收集运行时文档里内联在属性中的枚举值集合(springdoc 默认内联枚举,不建独立 schema)。"""
    enums: List[List[str]] = []
    for schema in (live.get("components") or {}).get("schemas", {}).values():
        for prop in (schema.get("properties") or {}).values():
            enum = prop.get("enum")
            if enum:
                enums.append([str(v) for v in enum])
    return enums


def _parse_ignored(ignored) -> set:
    """解析忽略清单:'GET /api/ping' 或 '/api/ping'(不限 method)两种格式 → 归一化集合。"""
    out = set()
    for item in ignored or []:
        item = str(item).strip()
        if not item:
            continue
        if item.upper().startswith(("GET ", "POST ", "PUT ", "PATCH ", "DELETE ")):
            out.add((item.split(" ", 1)[0].upper(), item.split(" ", 1)[1].strip()))
        else:
            out.add(("*", item))
    return out


def _is_ignored(method: str, path: str, ignored: set) -> bool:
    return (method, path) in ignored or ("*", path) in ignored


def compare_contract_with_live(contract_model: dict, live: dict, strict_required: bool = False,
                               ignored_paths=None) -> dict:
    """纯函数比对:契约规范化模型 vs 运行时 OpenAPI 文档。返回 {"ok", "issues", 统计}。

    strict_required=False(默认):运行时未声明 required(如 springdoc 无 Bean Validation
    注解时不导出 required)视为「未知」不比对;True:严格比对(适合 DTO 标注了
    @JsonProperty(required=true) / Bean Validation 的团队)。
    """
    issues: List[str] = []
    inline_enums = _inline_enums(live)
    ignored = _parse_ignored(ignored_paths)

    # 1/2. 路由与 operationId
    contract_eps = {(e["method"], e["path"]): e["operation_id"] for e in contract_model["endpoints"]}
    live_eps = _live_endpoints(live)
    for key in sorted(set(contract_eps) - set(live_eps)):
        issues.append(f"路由缺失: 运行时未实现 {key[0]} {key[1]}(契约 operationId={contract_eps[key]})")
    for key in sorted(set(live_eps) - set(contract_eps)):
        if _is_ignored(key[0], key[1], ignored):
            continue
        issues.append(f"路由多余: 运行时多出 {key[0]} {key[1]}(契约未定义)")
    for key in sorted(set(contract_eps) & set(live_eps)):
        c_opid, l_opid = contract_eps[key], live_eps[key]
        if l_opid and c_opid and l_opid != c_opid:
            issues.append(f"operationId 不一致: {key[0]} {key[1]} 契约={c_opid} 运行时={l_opid}")

    # 3/4/5. schema 字段/required/枚举
    live_schemas: Dict[str, dict] = (live.get("components") or {}).get("schemas") or {}
    for name in sorted(contract_model["schemas"]):
        c_schema = contract_model["schemas"][name] or {}
        l_name = _match_live_schema_name(live_schemas, name)
        if l_name is None:
            # 枚举模型被运行时内联导出(springdoc 默认行为):在属性内找集合一致的枚举
            c_enum = c_schema.get("enum")
            if c_enum and [str(v) for v in c_enum] in inline_enums:
                continue
            issues.append(f"模型缺失: 运行时未导出 {name}")
            continue
        l_schema = live_schemas[l_name] or {}
        c_props = set((c_schema.get("properties") or {}).keys())
        l_props = set((l_schema.get("properties") or {}).keys())
        for p in sorted(c_props - l_props):
            issues.append(f"字段缺失: {name}.{p} 契约有,运行时未导出(疑似序列化漂移)")
        for p in sorted(l_props - c_props):
            issues.append(f"字段多余: {name}.{p} 运行时导出,契约未定义")
        c_required = set(c_schema.get("required") or [])
        l_required = set(l_schema.get("required") or [])
        # 运行时未声明 required 且非严格模式 → 视为未知,不比对
        if (strict_required or l_required) and c_required != l_required:
            issues.append(
                f"required 不一致: {name} 契约={sorted(c_required)} 运行时={sorted(l_required)}"
            )
        c_enum = (c_schema.get("enum") or None)
        l_enum = (l_schema.get("enum") or None)
        if c_enum and l_enum and sorted(map(str, c_enum)) != sorted(map(str, l_enum)):
            issues.append(f"枚举漂移: {name} 契约={c_enum} 运行时={l_enum}")

    return {
        "ok": not issues,
        "issues": issues,
        "stats": {
            "contract_routes": len(contract_eps),
            "live_routes": len(live_eps),
            "contract_models": len(contract_model["schemas"]),
        },
    }


def live_check(contract_path: str | Path, live_url: str, timeout: float = 10.0,
              strict_required: bool = False, ignored_paths=None) -> dict:
    """入口:契约文件 + 运行时文档 URL → 比对结果。ignored_paths: 基础设施端点豁免(如 /api/ping)。"""
    model = parse_contract(contract_path)
    live = fetch_live_doc(live_url, timeout=timeout)
    result = compare_contract_with_live(model, live, strict_required=strict_required,
                                        ignored_paths=ignored_paths)
    result["live_url"] = live_url
    return result
