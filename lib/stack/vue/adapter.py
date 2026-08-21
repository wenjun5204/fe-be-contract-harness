#!/usr/bin/env python3
"""Vue 前端代码生成器:契约 → TS 类型 + API 请求层。

Vue 3 + TypeScript 与 React 共享同一套 OpenAPI→TS 类型映射(见 lib/stack/common.py)。
M2 阶段生成类型 + 请求层;组合式 API(composable)封装留待后续里程碑。
"""
from __future__ import annotations

import re
from typing import List

from lib.stack.adapter import GeneratedFile, StackAdapter, register
from lib.stack.common import collect_refs, ts_interface, ts_type


@register
class VueStackAdapter(StackAdapter):
    name = "vue"
    kind = "frontend"
    LINT = ["eslint src", "vue-tsc --noEmit"]
    BUILD = ["vite build"]
    TEST = ["vitest run"]
    COVERAGE = "vitest run --coverage"
    MARKERS = ["vite.config.ts", "src/App.vue"]

    def generate(self, model: dict) -> List[GeneratedFile]:
        schemas = model.get("schemas", {})
        endpoints = model.get("endpoints", [])
        return [
            self._types_file(schemas),
            self._client_file(endpoints, schemas),
            self.manifest(
                routes=[ep["operation_id"] for ep in endpoints],
                models=list(schemas.keys()),
            ),
        ]

    @staticmethod
    def _types_file(schemas: dict) -> GeneratedFile:
        lines = [
            "// 自动生成:契约派生类型(勿手改,重生成会覆盖)",
            "",
        ]
        for name, schema in schemas.items():
            lines.append(ts_interface(name, schema, schemas))
            lines.append("")
        return GeneratedFile("src/types/api.ts", "\n".join(lines))

    @staticmethod
    def _client_file(endpoints: list, schemas: dict) -> GeneratedFile:
        referenced = set()
        for ep in endpoints:
            referenced |= collect_refs(ep.get("request_schema"))
            referenced |= collect_refs(ep.get("response_schema"))
        lines = [
            "// 自动生成:契约派生请求层(勿手改,重生成会覆盖)",
            "// Vue 项目可直接使用,或封装为组合式 API(composable)",
            "",
        ]
        if referenced:
            lines.append(f"import type {{ {', '.join(sorted(referenced))} }} from '../types/api';")
            lines.append("")
        for ep in endpoints:
            lines.append(VueStackAdapter._client_fn(ep, schemas))
            lines.append("")
        return GeneratedFile("src/api/client.ts", "\n".join(lines))

    @staticmethod
    def _client_fn(ep: dict, schemas: dict) -> str:
        opid = ep["operation_id"]
        method = ep["method"]
        path = ep["path"]
        resp_ts = ts_type(ep.get("response_schema"), schemas)
        args = [f"{p}: string" for p in re.findall(r"\{([^}]+)\}", path)]
        if ep.get("request_schema"):
            args.append(f"body: {ts_type(ep['request_schema'], schemas)}")
        sig = f"export async function {opid}({', '.join(args)}): Promise<{resp_ts}> {{"
        return (
            f"{sig}\n"
            f"  // TODO: 实现请求 {method} {path}\n"
            f"  throw new Error('Not implemented: {opid}');\n"
            f"}}"
        )
