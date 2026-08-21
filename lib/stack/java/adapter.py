#!/usr/bin/env python3
"""Java(Spring) 后端代码生成器:契约 → POJO DTO + Controller 骨架。"""
from __future__ import annotations

import re
from typing import List

from lib.stack.adapter import GeneratedFile, StackAdapter, register
from lib.stack.common import collect_refs


def java_type(schema: dict, schemas: dict) -> str:
    """OpenAPI schema → Java 类型字符串。"""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    t = schema.get("type")
    if t == "string":
        return "String"
    if t == "integer":
        return "Integer"
    if t == "number":
        return "Double"
    if t == "boolean":
        return "Boolean"
    if t == "array":
        return f"List<{java_type(schema.get('items', {}), schemas)}>"
    return "Object"


METHOD_ANNOTATIONS = {
    "GET": "GetMapping",
    "POST": "PostMapping",
    "PUT": "PutMapping",
    "PATCH": "PatchMapping",
    "DELETE": "DeleteMapping",
}


@register
class JavaStackAdapter(StackAdapter):
    name = "java"
    kind = "backend"
    LINT = ["mvn checkstyle:check"]
    BUILD = ["mvn -q compile"]
    TEST = ["mvn test"]
    COVERAGE = "mvn test jacoco:report"
    MARKERS = ["pom.xml", "build.gradle"]
    DEPLOY = ["container"]

    def generate(self, model: dict) -> List[GeneratedFile]:
        schemas = model.get("schemas", {})
        endpoints = model.get("endpoints", [])
        files: List[GeneratedFile] = []
        for name, schema in schemas.items():
            files.append(GeneratedFile(f"src/main/java/dto/{name}.java", self._pojo(name, schema, schemas)))
        for resource, eps in self._group_by_resource(endpoints).items():
            files.append(GeneratedFile(
                f"src/main/java/controller/{self._pascal(resource)}Controller.java",
                self._controller(resource, eps, schemas),
            ))
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
            groups.setdefault(seg or "root", []).append(ep)
        return groups

    @staticmethod
    def _pascal(s: str) -> str:
        return "".join(p.capitalize() for p in re.split(r"[^a-zA-Z0-9]+", s) if p)

    @staticmethod
    def _cap(s: str) -> str:
        return s[:1].upper() + s[1:] if s else s

    def _pojo(self, name: str, schema: dict, schemas: dict) -> str:
        props = schema.get("properties", {})
        lines = [f"// 自动生成 DTO:{name}(勿手改)", f"public class {name} {{"]
        for p, ps in props.items():
            lines.append(f"    private {java_type(ps, schemas)} {p};")
        lines.append("")
        for p, ps in props.items():
            jt = java_type(ps, schemas)
            cap = self._cap(p)
            lines.append(f"    public {jt} get{cap}() {{ return {p}; }}")
            lines.append(f"    public void set{cap}({jt} {p}) {{ this.{p} = {p}; }}")
        lines.append("}")
        return "\n".join(lines) + "\n"

    def _controller(self, resource: str, eps: list, schemas: dict) -> str:
        class_name = self._pascal(resource) + "Controller"
        referenced = set()
        for ep in eps:
            referenced |= collect_refs(ep.get("request_schema"))
            referenced |= collect_refs(ep.get("response_schema"))
        imports = [
            "import java.util.List;",
            "import org.springframework.web.bind.annotation.*;",
        ] + [f"import dto.{n};" for n in sorted(referenced)]
        lines = [
            "// 自动生成:契约派生 Controller 骨架(勿手改,重生成会覆盖)",
            *imports,
            "",
            "@RestController",
            f'@RequestMapping("/{resource}")',
            f"public class {class_name} {{",
        ]
        for ep in eps:
            lines.extend(self._controller_method(ep, schemas, resource))
            lines.append("")
        lines.append("}")
        return "\n".join(lines) + "\n"

    def _controller_method(self, ep: dict, schemas: dict, resource: str) -> List[str]:
        ann = METHOD_ANNOTATIONS[ep["method"]]
        prefix = "/" + resource
        route = "" if ep["path"] == prefix else ep["path"][len(prefix):]
        resp_ts = java_type(ep.get("response_schema"), schemas)
        params = re.findall(r"\{([^}]+)\}", ep["path"])
        args = [f"@PathVariable String {p}" for p in params]
        if ep.get("request_schema"):
            args.append(f"@RequestBody {java_type(ep['request_schema'], schemas)} body")
        deco = f'@{ann}("{route}")' if route else f"@{ann}"
        sig = f"    {deco}\n    public {resp_ts} {ep['operation_id']}({', '.join(args)}) {{"
        return [sig, f"        throw new UnsupportedOperationException(\"Not implemented: {ep['operation_id']}\");", "    }"]
