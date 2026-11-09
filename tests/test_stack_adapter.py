#!/usr/bin/env python3
"""StackAdapter 命令映射 + 项目识别自测。运行:python3 tests/test_stack_adapter.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.stack.adapter import get_adapter  # noqa: E402


def test_commands():
    expected = {
        "react": ("tsc", "vitest"),
        "vue": ("vue-tsc", "vitest"),
        "node": ("eslint", "jest"),
        "java": ("mvn", "jacoco"),
    }
    for name, (lint_sig, cov_sig) in expected.items():
        a = get_adapter(name)
        assert a.lint_commands(), name
        assert a.build_commands(), name
        assert a.test_commands(), name
        assert a.coverage_command(), name
        assert lint_sig in " ".join(a.lint_commands()), name
        assert cov_sig in a.coverage_command(), name
        assert a.deploy_adapters(), name


def test_deploy():
    assert get_adapter("react").deploy_adapters() == ["static"]
    assert get_adapter("vue").deploy_adapters() == ["static"]
    assert get_adapter("node").deploy_adapters() == ["container"]
    assert get_adapter("java").deploy_adapters() == ["container"]


def test_java_mvnw_wrapper_preference():
    """mvnw wrapper 仓库优先 wrapper(真实首跑发现:wrapper 仓库本机无系统
    maven,mvn 命令不存在);无 wrapper 时回退系统 mvn;无 repo_path 时不变。"""
    a = get_adapter("java")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pom.xml").write_text("<project/>", encoding="utf-8")
        # 无 wrapper → 系统 mvn
        assert a.test_commands(d) == ["mvn test"], a.test_commands(d)
        # 带 wrapper → ./mvnw(cwd 相对形态,沙箱以 workdir 为 cwd 执行)
        (Path(d) / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")
        assert a.test_commands(d) == ["./mvnw test"], a.test_commands(d)
        assert a.build_commands(d) == ["./mvnw -q compile"], a.build_commands(d)
        assert a.coverage_command(d).startswith("./mvnw ")
    # 不传 repo_path → 维持原常量形态(向后兼容)
    assert a.test_commands() == ["mvn test"]
    # 其他栈不受 repo_path 影响
    assert get_adapter("node").test_commands(str(Path(tempfile.gettempdir()))) == get_adapter("node").test_commands()


def test_resource_groups_version_prefix():
    """真实首跑发现(Stripe 612 端点全量 /v1/*):首段分组退化成单个巨型
    V1Controller(612 方法/3237 行)。版本前缀感知分组按业务资源分组。"""
    from lib.stack.common import resource_groups, resource_name
    eps = [
        {"path": "/v1/charges", "method": "GET", "operation_id": "list_charges"},
        {"path": "/v1/charges/{id}", "method": "GET", "operation_id": "get_charge"},
        {"path": "/v1/customers", "method": "POST", "operation_id": "create_customer"},
        {"path": "/pets", "method": "GET", "operation_id": "list_pets"},
        {"path": "/pets/{id}", "method": "GET", "operation_id": "get_pet"},
    ]
    g = resource_groups(eps)
    assert set(g) == {"/v1/charges", "/v1/customers", "/pets"}, g
    assert resource_name("/v1/charges") == "charges"
    assert resource_name("/pets") == "pets"


def test_java_codegen_versioned_controllers():
    """版本化路径生成:ChargesController(@RequestMapping("/v1/charges") +
    子路由 "/{id}");小契约 PetsController 行为不变。"""
    model = {
        "schemas": {"Charge": {"properties": {"id": {"type": "string"}}}},
        "endpoints": [
            {"path": "/v1/charges", "method": "GET", "operation_id": "list_charges",
             "response_schema": {"$ref": "#/components/schemas/Charge"}},
            {"path": "/v1/charges/{id}", "method": "GET", "operation_id": "get_charge"},
            {"path": "/pets", "method": "GET", "operation_id": "list_pets"},
        ],
    }
    a = get_adapter("java")
    files = {f.path: f.content for f in a.generate(model)}
    assert "src/main/java/controller/ChargesController.java" in files, sorted(files)
    c = files["src/main/java/controller/ChargesController.java"]
    assert '@RequestMapping("/v1/charges")' in c, c[:300]
    assert '@GetMapping("/{id}")' in c
    assert "V1Controller" not in files


def test_node_codegen_versioned_controllers():
    """node 栈同样按资源分组(不再退化为单个 v1.controller.ts)。"""
    model = {
        "schemas": {"Charge": {"properties": {"id": {"type": "string"}}}},
        "endpoints": [
            {"path": "/v1/charges", "method": "GET", "operation_id": "list_charges",
             "response_schema": {"$ref": "#/components/schemas/Charge"}},
            {"path": "/v1/charges/{id}", "method": "GET", "operation_id": "get_charge"},
        ],
    }
    a = get_adapter("node")
    files = {f.path: f.content for f in a.generate(model)}
    assert "src/controllers/charges.controller.ts" in files, sorted(files)
    c = files["src/controllers/charges.controller.ts"]
    assert "@Controller('v1/charges')" in c, c[:300]
    assert "@Get('/:id')" in c or "@Get('/:id')" in c.replace('"', "'")


def test_detect():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "pom.xml").write_text("<project/>", encoding="utf-8")
        r = get_adapter("java").detect(d)
        assert r["detected"] and "pom.xml" in r["evidence"], r
        # 无 React 标记 → 未识别
        r = get_adapter("react").detect(d)
        assert not r["detected"], r


def main():
    test_commands()
    test_detect()
    test_deploy()
    test_java_mvnw_wrapper_preference()
    test_resource_groups_version_prefix()
    test_java_codegen_versioned_controllers()
    test_node_codegen_versioned_controllers()
    print("OK: stack_adapter 自测通过(7 组断言)")


if __name__ == "__main__":
    main()
