#!/usr/bin/env python3
"""M3 契约一致性校验 + 漂移检测(设计文档 §8.2 / §14.5)。

1. 跨栈一致性(cross_stack_check):后端/前端各栈生成产物对契约的覆盖是否一致;
2. 漂移检测(drift_check):契约重生成的期望 manifest 与磁盘上已有产物是否一致。

这是 contract-drift-guard hook 的确定性核心:hook 在提交前调用,漂移即 fail-closed 阻断。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lib.contract.parser import parse_contract
from lib.stack.adapter import get_adapter


def check_manifest_coverage(
    manifest: dict, contract_routes: set, contract_models: set
) -> Tuple[bool, bool]:
    """校验 manifest 是否完整覆盖契约的 routes/models(纯函数,便于单测)。"""
    routes = set(manifest.get("routes", []))
    models = set(manifest.get("models", []))
    return routes == contract_routes, models == contract_models


def cross_stack_check(contract_path: str | Path, stacks: Optional[List[str]] = None) -> dict:
    """跨栈一致性:各栈生成产物对契约的覆盖一致且完整。"""
    model = parse_contract(contract_path)
    stacks = stacks or ["react", "vue", "react_native", "expo", "node", "java"]
    contract_routes = {e["operation_id"] for e in model["endpoints"]}
    contract_models = set(model["schemas"].keys())

    per_stack: Dict[str, dict] = {}
    ok = True
    for s in stacks:
        adapter = get_adapter(s)
        files = {f.path: f.content for f in adapter.generate(model)}
        manifest = json.loads(files["codegen-manifest.json"])
        routes_ok, models_ok = check_manifest_coverage(manifest, contract_routes, contract_models)
        per_stack[s] = {"routes_ok": routes_ok, "models_ok": models_ok}
        ok = ok and routes_ok and models_ok

    return {
        "ok": ok,
        "contract_routes": sorted(contract_routes),
        "contract_models": sorted(contract_models),
        "per_stack": per_stack,
    }


def drift_check(contract_path: str | Path, stack: str, gen_dir: str | Path) -> dict:
    """漂移检测:重生成期望产物,与磁盘上已有 codegen-manifest.json 对比。

    E2 知识回流:检出真实漂移(非"缺 manifest")时自动写一条 backend assumption
    条目——下次同栈阶段的 dispatch context 可见"上次漂移记录"。AI 推断一律
    assumption,升级 confirmed 必须人经 confirm_entry(三方分工)。
    落库失败不影响检测结果(回流是旁路,不阻断主流程)。
    """
    model = parse_contract(contract_path)
    adapter = get_adapter(stack)
    expected = {f.path: f.content for f in adapter.generate(model)}
    expected_manifest = json.loads(expected["codegen-manifest.json"])

    manifest_path = Path(gen_dir) / "codegen-manifest.json"
    if not manifest_path.exists():
        return {
            "ok": False,
            "reason": f"缺少 {manifest_path}(未生成或未提交)",
            "routes_drift": True,
            "models_drift": True,
        }
    on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    routes_drift = set(on_disk.get("routes", [])) != set(expected_manifest["routes"])
    models_drift = set(on_disk.get("models", [])) != set(expected_manifest["models"])
    result = {
        "ok": not (routes_drift or models_drift),
        "routes_drift": routes_drift,
        "models_drift": models_drift,
        "expected_routes": expected_manifest["routes"],
        "on_disk_routes": on_disk.get("routes", []),
    }
    if routes_drift or models_drift:
        try:
            from lib.domain_knowledge import write_entry
            payload = {
                "id": f"drift-{stack}-{Path(contract_path).stem}",
                "domain": "backend",
                "entity": "CodegenDrift",
                "type": "convention",
                "status": "assumption",
                "source": "drift_check",
                "fields": [],
                "states": [],
                "error_codes": [],
                "content": (
                    f"契约漂移记录({stack} 栈,契约 {Path(contract_path).name}):"
                    f"routes_drift={routes_drift}, models_drift={models_drift}。"
                    f"期望路由 {sorted(expected_manifest['routes'])} vs "
                    f"磁盘 {sorted(on_disk.get('routes', []))}。"
                    "生成产物与最新契约不一致,重新生成或人工核对差异后经 confirm 确认处理结论。"
                ),
            }
            # 幂等:同 id 重复检出覆盖更新(assumption 内容是最新漂移状态,无历史价值;
            # find_conflicts 防线只对 confirmed 生效,assumption 覆盖不越权)
            write_entry(payload, mode="replace")
            result["knowledge_feedback"] = "assumption 条目已落库(待人工 confirm)"
        except Exception as e:  # noqa: BLE001 —— 回流旁路,失败不阻断检测
            result["knowledge_feedback"] = f"回流失败(不影响检测): {e}"
    return result
