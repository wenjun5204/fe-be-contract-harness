#!/usr/bin/env python3
"""React Native 前端代码生成器:契约 → TS 类型 + fetch 请求层。

与 React Web 共享同一套 OpenAPI→TS 类型映射(lib/stack/common.py);
差异只在工程命令映射与部署路由:
- BUILD 门用 tsc 类型检查(确定性、沙箱白名单友好),真机 metro bundle 归 CI/发布;
- MARKERS 只取裸 RN 工程特征(ios/android 原生目录)。Expo 托管工程由
  expo 栈(本适配器子类)识别,app.config.* 是 Expo 独有标记。
"""
from __future__ import annotations

import re
from typing import List

from lib.stack.adapter import GeneratedFile, StackAdapter, register
from lib.stack.common import collect_refs, ts_interface, ts_type


@register
class ReactNativeStackAdapter(StackAdapter):
    name = "react_native"
    kind = "frontend"
    LINT = ["eslint src --ext .ts,.tsx", "tsc --noEmit"]
    BUILD = ["tsc --noEmit"]
    TEST = ["jest"]
    COVERAGE = "jest --coverage"
    MARKERS = ["ios/Podfile", "android/app", "metro.config.js"]
    DEPLOY = ["app-bundle"]

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
            "// TODO: 替换为项目内统一的请求封装(RN 自带全局 fetch,可直接实现)",
            "",
        ]
        if referenced:
            lines.append(f"import type {{ {', '.join(sorted(referenced))} }} from '../types/api';")
            lines.append("")
        for ep in endpoints:
            lines.append(ReactNativeStackAdapter._client_fn(ep, schemas))
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
