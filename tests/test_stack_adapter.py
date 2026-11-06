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
    print("OK: stack_adapter 自测通过(4 组断言)")


if __name__ == "__main__":
    main()
