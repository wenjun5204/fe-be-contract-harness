#!/usr/bin/env python3
"""Tool Registry 自测。运行:python3 tests/test_tool_registry.py"""
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
    assert len(schemas) == 10  # 9 + run_tests(Stage 8 闭环)
    for s in schemas:
        assert s["type"] == "function"
        fn = s["function"]
        assert fn["name"] and fn["description"] and fn["parameters"]["type"] == "object"
    names = {s["function"]["name"] for s in schemas}
    assert {"read_contract", "verify_codegen", "consistency_check",
            "query_knowledge", "read_file", "write_file", "query_symbols",
            "run_check", "run_tests", "report_outputs"} == names
    # run_check 参数无命令字段(执行类工具安全底线:命令只能来自白名单)
    run_check = next(s for s in schemas if s["function"]["name"] == "run_check")
    assert set(run_check["function"]["parameters"]["properties"]) == {"kind", "stack", "timeout"}


def test_task_path_injection_blocked():
    """A 沙箱补全:任务输入路径拦截注入形态;合法 workdir 外绝对路径放行。"""
    tools = build_default_tools(CONTRACT)
    # .. 逃逸段
    for bad in ["../../etc/passwd", "a/../../secrets.yaml", "x\u0000.yaml",
                "contract.yaml\u0000", "$(cat /etc/passwd)", "`rm -rf`"]:
        if "\u0000" in bad:
            bad = bad.replace("\u0000", "\x00")
        res = tools.execute("read_contract", {"path": bad})
        assert not res["ok"] and ("注入" in res["error"] or "非法" in res["error"]), (bad, res)
    # verify_codegen 的 contract/out_dir 同样拦截
    res = tools.execute("verify_codegen",
                        {"contract": "../../etc/passwd", "stack": "node", "out_dir": "gen"})
    assert not res["ok"] and "注入" in res["error"], res
    # 合法绝对路径(契约可放 workdir 外)放行——不存在的文件报解析错误而非注入拦截
    res = tools.execute("read_contract", {"path": "/tmp/nonexistent-contract.yaml"})
    assert not res["ok"] and "不存在" in res["error"] and "注入" not in res["error"], res


def test_query_symbols_and_read_file_paging():
    """P1-4: query_symbols 结构化检索 + read_file 翻页/截断提示(ACI 紧凑化)。"""
    with tempfile.TemporaryDirectory() as d:
        # 造一个带符号的源文件和一个长文件
        (Path(d) / "svc.py").write_text(
            "class Order:\n    pass\n\ndef create_order():\n    return Order()\n", encoding="utf-8")
        (Path(d) / "long.txt").write_text("\n".join(f"line-{i}" for i in range(1, 501)), encoding="utf-8")
        tools = build_default_tools(CONTRACT, workdir=d)

        # 定义查询
        res = tools.execute("query_symbols", {"symbol": "Order", "kind": "definition"})
        assert res["ok"], res
        assert res["definitions"] and res["definitions"][0]["file"] == "svc.py", res
        assert res["definitions"][0]["kind"] == "class"
        # 引用查询
        res = tools.execute("query_symbols", {"symbol": "Order", "kind": "references"})
        assert res["ok"] and "svc.py" in res["reference_files"], res
        # 未知符号不报错,给自纠错提示
        res = tools.execute("query_symbols", {"symbol": "NoSuchThing"})
        assert res["ok"] and "hint" in res, res

        # read_file 默认 200 行 + 翻页提示
        res = tools.execute("read_file", {"path": "long.txt"})
        assert res["ok"] and res["truncated"], res
        assert res["lines"] == {"offset": 1, "returned": 200, "total": 500}
        assert "offset=201" in res["hint"], res
        # 翻页续读:offset=201 起 50 行(文件还有剩余 → 仍 truncated,提示下一起点)
        res = tools.execute("read_file", {"path": "long.txt", "offset": 201, "limit": 50})
        assert res["lines"] == {"offset": 201, "returned": 50, "total": 500}, res
        assert res["truncated"] and "offset=251" in res["hint"], res
        assert res["content"].startswith("line-201"), res
        # 读到文件末尾 → 不再 truncated
        res = tools.execute("read_file", {"path": "long.txt", "offset": 451, "limit": 100})
        assert not res["truncated"] and "hint" not in res, res


def test_execute_read_contract():
    tools = build_default_tools(CONTRACT)
    res = tools.execute("read_contract", {})
    assert res["ok"], res
    assert res["entities"], "petstore 应解析出实体"
    # 小契约(≤50 实体)概览行为不变:带 schema 明细、无截断提示
    assert res["schemas"] and "entities_note" not in res, res


def test_read_contract_bounded_output_at_scale():
    """真实首跑发现(Stripe 1538 实体):read_contract 全量返回 178k 字符,
    一次调用打爆上下文。输出保护:实体 ≤200 + 翻页、schema 明细 ≤50、
    endpoints ≤100;单实体详情模式 entity=<name> 提供检索路径。"""
    import json
    with tempfile.TemporaryDirectory() as d:
        big = Path(d) / "big.json"
        schemas = {
            f"S{i}": {"type": "object", "properties": {f"f{j}": {"type": "string"} for j in range(5)}}
            for i in range(250)
        }
        paths = {
            f"/v1/r{i}": {"get": {"operationId": f"get_r{i}",
                                  "responses": {"200": {"description": "ok",
                                                        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/S{i}"}}}}}}}
            for i in range(150)
        }
        big.write_text(json.dumps({
            "openapi": "3.0.0", "info": {"title": "big", "version": "1"},
            "paths": paths, "components": {"schemas": schemas},
        }), encoding="utf-8")
        tools = build_default_tools(str(big))
        res = tools.execute("read_contract", {})
        assert res["ok"], res
        assert len(res["entities"]) == 200, len(res["entities"])
        assert res["stats"] == {"entities": 250, "endpoints": 150}, res["stats"]
        assert "entities_note" in res and "翻页" in res["entities_note"]
        assert "schemas" not in res and "schemas_note" in res  # >50 不带明细
        assert len(res["endpoints"]) == 100
        # 有界性:整体输出 < 12k 字符(Stripe 实测 178k → 预期 ~1-2 个数量级压缩)
        assert len(json.dumps(res, ensure_ascii=False)) < 12_000
        # 翻页
        res2 = tools.execute("read_contract", {"entities_offset": 200})
        assert len(res2["entities"]) == 50, res2["entities"]
        # 单实体详情:全量字段 + 相关端点
        res3 = tools.execute("read_contract", {"entity": "S0"})
        assert res3["ok"], res3
        assert len(res3["fields"]) == 5, res3
        assert any(e.get("path") == "/v1/r0" for e in res3["endpoints"]), res3["endpoints"]
        # 不存在的实体:可行动报错(附检索方式)
        res4 = tools.execute("read_contract", {"entity": "NoSuchEntity"})
        assert not res4["ok"] and "entities_offset" in res4["error"], res4


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
    test_task_path_injection_blocked()
    test_query_symbols_and_read_file_paging()
    test_file_tools_and_path_safety()
    test_safe_join_units()
    test_report_outputs_terminal()
    test_custom_registry()
    print("OK: tool_registry 自测通过(10 组断言)")


if __name__ == "__main__":
    main()
