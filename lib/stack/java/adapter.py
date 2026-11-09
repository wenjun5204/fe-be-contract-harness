#!/usr/bin/env python3
"""Java(Spring) 后端代码生成器:契约 → POJO DTO + Controller 骨架。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from lib.stack.adapter import GeneratedFile, StackAdapter, register
from lib.stack.common import collect_refs, resource_groups, resource_name


def java_type(schema: dict, schemas: dict) -> str:
    """OpenAPI schema → Java 类型字符串。"""
    if not schema:
        # 与 TS 侧 ts_type(None) -> "void" 对齐:无 JSON 2xx 响应(如二进制回图端点)
        return "void"
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
    # jacoco 全限定 goal 形态:无需 pom 预先配置插件(真实首跑发现:仓库 pom
    # 常无 jacoco 插件,裸 `test jacoco:report` 无 agent 产不出报告);
    # 报告落 target/site/jacoco/jacoco.csv,由 coverage_collector 解析。
    _JACOCO_VERSION = "0.8.12"
    COVERAGE = (
        f"mvn org.jacoco:jacoco-maven-plugin:{_JACOCO_VERSION}:prepare-agent "
        f"test org.jacoco:jacoco-maven-plugin:{_JACOCO_VERSION}:report"
    )
    MARKERS = ["pom.xml", "build.gradle"]
    DEPLOY = ["container"]

    def _mvn(self, repo_path: "str | Path | None" = None) -> str:
        """mvn 命令形态:仓库带 mvnw wrapper 时优先 wrapper(真实首跑发现:
        wrapper 仓库是常态,本机未必装系统 maven,mvn 直接命令不存在)。

        wrapper 形态 "./mvnw" 由 cwd 相对解析(sandbox 以 workdir 为 cwd);
        仅做文件存在性探测,命令内容仍源自本常量派生,LLM 不可控。
        """
        if repo_path and (Path(repo_path) / "mvnw").exists():
            return "./mvnw"
        return "mvn"

    def lint_commands(self, repo_path: "str | Path | None" = None) -> List[str]:
        return [f"{self._mvn(repo_path)} checkstyle:check"]

    def build_commands(self, repo_path: "str | Path | None" = None) -> List[str]:
        return [f"{self._mvn(repo_path)} -q compile"]

    def test_commands(self, repo_path: "str | Path | None" = None) -> List[str]:
        return [f"{self._mvn(repo_path)} test"]

    def coverage_command(self, repo_path: "str | Path | None" = None) -> str:
        mvn = self._mvn(repo_path)
        return (
            f"{mvn} org.jacoco:jacoco-maven-plugin:{self._JACOCO_VERSION}:prepare-agent "
            f"test org.jacoco:jacoco-maven-plugin:{self._JACOCO_VERSION}:report"
        )

    def generate(self, model: dict) -> List[GeneratedFile]:
        schemas = model.get("schemas", {})
        endpoints = model.get("endpoints", [])
        files: List[GeneratedFile] = []
        for name, schema in schemas.items():
            files.append(GeneratedFile(f"src/main/java/dto/{name}.java", self._pojo(name, schema, schemas)))
        for base, eps in resource_groups(endpoints).items():
            files.append(GeneratedFile(
                f"src/main/java/controller/{self._pascal(resource_name(base))}Controller.java",
                self._controller(base, eps, schemas),
            ))
        files.append(self.manifest(
            routes=[ep["operation_id"] for ep in endpoints],
            models=list(schemas.keys()),
        ))
        return files

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

    def _controller(self, base: str, eps: list, schemas: dict) -> str:
        class_name = self._pascal(resource_name(base)) + "Controller"
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
            f'@RequestMapping("{base}")',
            f"public class {class_name} {{",
        ]
        for ep in eps:
            lines.extend(self._controller_method(ep, schemas, base))
            lines.append("")
        lines.append("}")
        return "\n".join(lines) + "\n"

    def _controller_method(self, ep: dict, schemas: dict, base: str) -> List[str]:
        ann = METHOD_ANNOTATIONS[ep["method"]]
        route = "" if ep["path"] == base else ep["path"][len(base):]
        resp_ts = java_type(ep.get("response_schema"), schemas)
        params = re.findall(r"\{([^}]+)\}", ep["path"])
        args = [f"@PathVariable String {p}" for p in params]
        if ep.get("request_schema"):
            args.append(f"@RequestBody {java_type(ep['request_schema'], schemas)} body")
        deco = f'@{ann}("{route}")' if route else f"@{ann}"
        sig = f"    {deco}\n    public {resp_ts} {ep['operation_id']}({', '.join(args)}) {{"
        return [sig, f"        throw new UnsupportedOperationException(\"Not implemented: {ep['operation_id']}\");", "    }"]
