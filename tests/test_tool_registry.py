#!/usr/bin/env python3
"""Tool Registry 自测。运行:python3 tests/test_tool_registry.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tool_registry import (  # noqa: E402
    Tool,
    ToolError,
    ToolRegistry,
    build_default_tools,
    safe_join,
)

REPO = Path(__file__).resolve().parent.parent
CONTRACT = REPO / "examples" / "petstore.yaml"


def test_schemas_format():
    tools = build_default_tools(CONTRACT)
    schemas = tools.schemas()
    assert len(schemas) == 7
    for s in schemas:
        assert s["type"] == "function"
        fn = s["function"]
        assert fn["name"] and fn["description"] and fn["parameters"]["type"] == "object"
    names = {s["function"]["name"] for s in schemas}
    assert {"read_contract", "verify_codegen", "consistency_check",
            "query_knowledge", "read_file", "write_file", "report_outputs"} == names


def test_execute_read_contract():
    tools = build_default_tools(CONTRACT)
    res = tools.execute("read_contract", {})
    assert res["ok"], res
    assert res["entities"], "petstore 应解析出实体"


def test_args_validation():
    tools = build_default_tools(CONTRACT)
    # 缺必填
    res = tools.execute("query_knowledge", {})
    assert not res["ok"] and "缺少必填参数" in res["error"]
    # 未知参数
    res = tools.execute("query_knowledge", {"domain": "qa", "nope": 1})
    assert not res["ok"] and "不接受参数" in res["error"]
    # 类型错误
    res = tools.execute("query_knowledge", {"domain": 123})
    assert not res["ok"] and "类型" in res["error"]
    # 未知工具
    res = tools.execute("not_a_tool", {})
    assert not res["ok"] and "未知工具" in res["error"]


def test_query_knowledge():
    tools = build_default_tools(CONTRACT)
    res = tools.execute("query_knowledge", {"domain": "frontend"})
    assert res["ok"], res


def test_file_tools_and_path_safety():
    with tempfile.TemporaryDirectory() as d:
        tools = build_default_tools(CONTRACT, workdir=d)
        # 正常写入 + 读回
        res = tools.execute("write_file", {"path": "gen/a.txt", "content": "hello"})
        assert res["ok"], res
        res = tools.execute("read_file", {"path": "gen/a.txt"})
        assert res["ok"] and res["content"] == "hello"
        # 相对路径越界
        res = tools.execute("write_file", {"path": "../evil.txt", "content": "x"})
        assert not res["ok"] and "越界" in res["error"]
        assert not (Path(d).parent / "evil.txt").exists()
        # 绝对路径越界
        res = tools.execute("read_file", {"path": "/etc/passwd"})
        assert not res["ok"] and "越界" in res["error"]
        # 读不存在文件
        res = tools.execute("read_file", {"path": "missing.txt"})
        assert not res["ok"] and "不存在" in res["error"]


def test_safe_join_units():
    root = Path("/tmp/ws")
    assert safe_join(root, "a/b.txt") == (root / "a" / "b.txt").resolve()
    try:
        safe_join(root, "../outside.txt")
        raise AssertionError("应当拒绝越界")
    except ToolError:
        pass


def test_report_outputs_terminal():
    tools = build_default_tools(CONTRACT)
    assert tools.get("report_outputs").terminal is True
    res = tools.execute("report_outputs", {"outputs": {"test_cases": [{"id": "TC-1"}]}})
    assert res["ok"] and res["received"], res
    # 空 outputs 拒绝
    res = tools.execute("report_outputs", {"outputs": {}})
    assert not res["ok"]


def test_custom_registry():
    reg = ToolRegistry()
    reg.register(Tool(
        name="echo", description="回声", parameters={"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
        fn=lambda a: {"ok": True, "msg": a["msg"]},
    ))
    # 重名注册拒绝
    try:
        reg.register(reg.get("echo"))
        raise AssertionError("应当拒绝重复注册")
    except ValueError:
        pass
    assert reg.execute("echo", {"msg": "hi"}) == {"ok": True, "msg": "hi"}
    # 执行器异常不炸,收敛为 ok=false
    reg.register(Tool(name="boom", description="必炸", parameters={"type": "object", "properties": {}}, fn=lambda a: 1 / 0))
    res = reg.execute("boom", {})
    assert not res["ok"] and "ZeroDivisionError" in res["error"]


def main():
    test_schemas_format()
    test_execute_read_contract()
    test_args_validation()
    test_query_knowledge()
    test_file_tools_and_path_safety()
    test_safe_join_units()
    test_report_outputs_terminal()
    test_custom_registry()
    print("OK: tool_registry 自测通过(8 组断言)")


if __name__ == "__main__":
    main()
