#!/usr/bin/env python3
"""G1 生成门校验(设计文档 §14.3):生成即验证。

校验项:
1. 幂等性 —— 同一契约生成两次,产物字节一致(证明生成器无随机漂移);
2. 结构忠实性 —— codegen-manifest 覆盖契约的所有 endpoint 与 schema。
(可编译性校验依赖真实工具链,后续里程碑接入,见 §14.3。)
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.contract.parser import parse_contract
from lib.stack.adapter import get_adapter


def verify(contract_path: str | Path, stack_name: str) -> dict:
    model = parse_contract(contract_path)
    adapter = get_adapter(stack_name)

    first = {f.path: f.content for f in adapter.generate(model)}
    second = {f.path: f.content for f in adapter.generate(model)}
    idempotent = first == second

    manifest = json.loads(first.get("codegen-manifest.json", "{}"))
    expected_routes = [ep["operation_id"] for ep in model["endpoints"]]
    expected_models = list(model["schemas"].keys())
    routes_ok = set(expected_routes) <= set(manifest.get("routes", []))
    models_ok = set(expected_models) <= set(manifest.get("models", []))

    return {
        "ok": idempotent and routes_ok and models_ok,
        "idempotent": idempotent,
        "routes_ok": routes_ok,
        "models_ok": models_ok,
        "routes": expected_routes,
        "models": expected_models,
        "files": sorted(first.keys()),
    }
