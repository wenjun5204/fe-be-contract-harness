#!/usr/bin/env python3
"""Node(Nest) 后端代码生成器:契约 → DTO 类 + Controller 骨架。"""
from __future__ import annotations

import re
from typing import List

from lib.stack.adapter import GeneratedFile, StackAdapter, register
from lib.stack.common import nest_route, ts_class, ts_type

METHOD_DECORATORS = {
    "GET": "Get",
    "POST": "Post",
    "PUT": "Put",
    "PATCH": "Patch",
    "DELETE": "Delete",
}


@register
class NodeStackAdapter(StackAdapter):
    name = "node"
    kind = "backend"
    LINT = ["eslint src", "tsc --noEmit"]
    BUILD = ["nest build"]
    TEST = ["jest"]
    COVERAGE = "jest --coverage"
    MARKERS = ["nest-cli.json", "src/main.ts"]

    def generate(self, model: dict) -> List[GeneratedFile]:
        schemas = model.get("schemas", {})
        endpoints = model.get("endpoints", [])
        files: List[GeneratedFile] = []
        # 1. DTO 类 + barrel
        for name, schema in schemas.items():
            files.append(GeneratedFile(f"src/dto/{name}.dto.ts", ts_class(name, schema, schemas)))
        files.append(GeneratedFile(
            "src/dto/index.ts",
            "\n".join([f"export * from './{n}.dto';" for n in sorted(schemas.keys())]) + "\n",
        ))
        # 2. Controller(按资源分组)
        for resource, eps in self._group_by_resource(endpoints).items():
            files.append(GeneratedFile(
                f"src/controllers/{resource}.controller.ts",
                self._controller_file(resource, eps, schemas),
            ))
        # 3. manifest
        files.append(self.manifest(
            routes=[ep["operation_id"] for ep in endpoints],
            models=list(schemas.keys()),
        ))
        return files

    @staticmethod
    def _group_by_resource(endpoints: list) -> dict:
        groups: dict = {}
        for ep in endpoints:
            seg = ep["path"].strip("/").split("/")[0]
            resource = seg or "root"
            groups.setdefault(resource, []).append(ep)
        return groups

    @staticmethod
    def _pascal(s: str) -> str:
        return "".join(p.capitalize() for p in re.split(r"[^a-zA-Z0-9]+", s) if p)

    @staticmethod
    def _path_params(path: str) -> List[str]:
        return re.findall(r"\{([^}]+)\}", path)

    def _controller_file(self, resource: str, eps: list, schemas: dict) -> str:
        class_name = self._pascal(resource) + "Controller"
        decorators = sorted({METHOD_DECORATORS[ep["method"]] for ep in eps})
        needed = ["Controller"] + decorators + ["Body", "Param"]
        lines = [
            "// 自动生成:契约派生 Controller 骨架(勿手改,重生成会覆盖)",
            "import { " + ", ".join(needed) + " } from '@nestjs/common';",
            "",
            f"@Controller('{resource}')",
            f"export class {class_name} {{",
        ]
        for ep in eps:
            lines.extend(self._controller_method(ep, schemas, resource))
            lines.append("")
        lines.append("}")
        return "\n".join(lines)

    def _controller_method(self, ep: dict, schemas: dict, resource: str) -> List[str]:
        dec = METHOD_DECORATORS[ep["method"]]
        prefix = "/" + resource
        full = nest_route(ep["path"])  # /pets/:petId
        route = "" if full == prefix else full[len(prefix):]  # "/" 或 "/:petId" 或 ""
        resp_ts = ts_type(ep.get("response_schema"), schemas)
        args = [f"@Param('{p}') {p}: string" for p in self._path_params(ep["path"])]
        if ep.get("request_schema"):
            args.append(f"@Body() body: {ts_type(ep['request_schema'], schemas)}")
        deco = f"@{dec}('{route}')" if route else f"@{dec}()"
        sig = f"  {deco}\n  async {ep['operation_id']}({', '.join(args)}): Promise<{resp_ts}> {{"
        return [sig, f"    // TODO: 实现 {ep['method']} {ep['path']}", "    throw new Error('Not implemented');", "  }"]
