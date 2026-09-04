#!/usr/bin/env python3
"""OpenAPI 契约解析器 —— 读取 openapi.yaml/json,产出规范化契约模型。

规范化模型(codegen 消费):
{
  "info": {...},
  "schemas": { "<Name>": {schema} },          # components.schemas(命名 schema)
  "endpoints": [
    {
      "method": "GET", "path": "/pets", "operation_id": "listPets",
      "request_schema": {schema} | null,       # requestBody application/json schema
      "response_schema": {schema} | null       # 首个 2xx application/json schema
    }
  ]
}

schema 保留原始 $ref 与类型信息,由 codegen 层负责渲染(见 lib/stack/common.py)。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


class OpenAPIError(Exception):
    """契约解析错误。"""


def load_contract(path: str | Path) -> dict:
    """加载 OpenAPI 3.x 契约(YAML 或 JSON)。"""
    p = Path(path)
    if not p.exists():
        raise OpenAPIError(f"契约文件不存在: {p}")
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise OpenAPIError(
                "缺少 pyyaml 依赖(YAML 契约解析需要):请执行 python3 -m pip install pyyaml"
            ) from e
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise OpenAPIError("契约根节点必须是对象")
    if "openapi" not in data:
        raise OpenAPIError("缺少 openapi 版本字段(仅支持 OpenAPI 3.x)")
    return data


class OpenAPIParser:
    def __init__(self, contract: dict):
        self.raw = contract
        self.schemas: Dict[str, dict] = dict(
            contract.get("components", {}).get("schemas", {})
        )

    # ---- 静态工具 ----
    @staticmethod
    def _ref_name(schema: dict) -> Optional[str]:
        ref = schema.get("$ref")
        return ref.rsplit("/", 1)[-1] if ref else None

    @staticmethod
    def _json_schema(container: dict) -> Optional[dict]:
        """从 requestBody / response 容器提取 application/json schema。"""
        if not container:
            return None
        return container.get("content", {}).get("application/json", {}).get("schema")

    @staticmethod
    def _operation_id(method: str, path: str) -> str:
        base = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
        return f"{method}_{base}" if base else method

    @staticmethod
    def _first_success_schema(responses: dict) -> Optional[dict]:
        for status in sorted(responses.keys()):
            if str(status).startswith("2"):
                resp = responses[status]
                if isinstance(resp, dict):
                    return resp.get("content", {}).get("application/json", {}).get("schema")
        return None

    # ---- 端点解析 ----
    def endpoints(self) -> List[dict]:
        out: List[dict] = []
        for path, item in self.raw.get("paths", {}).items():
            if not isinstance(item, dict):
                continue
            for method in HTTP_METHODS:
                op = item.get(method)
                if not op:
                    continue
                opid = op.get("operationId") or self._operation_id(method, path)
                out.append({
                    "method": method.upper(),
                    "path": path,
                    "operation_id": opid,
                    "request_schema": self._json_schema(op.get("requestBody")),
                    "response_schema": self._first_success_schema(op.get("responses", {})),
                })
        return out

    def model(self) -> dict:
        return {
            "info": self.raw.get("info", {}),
            "schemas": self.schemas,
            "endpoints": self.endpoints(),
        }


def parse_contract(path: str | Path) -> dict:
    """入口:契约文件路径 → 规范化模型。"""
    return OpenAPIParser(load_contract(path)).model()
