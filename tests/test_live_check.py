#!/usr/bin/env python3
"""运行时契约校验(live check)自测:序列化漂移(isMine→mine 类)必须被检出。
运行:python3 tests/test_live_check.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.live_check import compare_contract_with_live  # noqa: E402
from lib.contract.parser import parse_contract  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def _live_doc_skeleton() -> dict:
    """按 petstore 契约构造一份「完全一致」的运行时 OpenAPI 文档。"""
    model = parse_contract(EXAMPLE)
    paths = {}
    for e in model["endpoints"]:
        op = {"operationId": e["operation_id"], "responses": {"200": {"description": "ok"}}}
        if e["request_schema"]:
            op["requestBody"] = {"content": {"application/json": {"schema": e["request_schema"]}}}
        paths.setdefault(e["path"], {})[e["method"].lower()] = op
    schemas = {}
    for name, schema in model["schemas"].items():
        schemas[name] = schema
    return {"openapi": "3.0.3", "paths": paths, "components": {"schemas": schemas}}


def test_live_check_pass_when_consistent():
    model = parse_contract(EXAMPLE)
    result = compare_contract_with_live(model, _live_doc_skeleton())
    assert result["ok"], result["issues"]
    assert result["stats"]["contract_routes"] == len(model["endpoints"])


def test_live_check_catches_serialization_drift():
    """Jackson 命名陷阱:契约 isMine,运行时序列化为 mine → 必须报字段缺失+多余。"""
    model = parse_contract(EXAMPLE)
    live = _live_doc_skeleton()
    # 找一个带 boolean 字段的 schema 做 isMine→mine 模拟;petstore 没有 boolean,
    # 直接取第一个 schema 的第一个字段做改名漂移
    first_name = sorted(model["schemas"])[0]
    first_prop = sorted(model["schemas"][first_name]["properties"])[0]
    live["components"]["schemas"][first_name]["properties"]["renamed_" + first_prop] = \
        live["components"]["schemas"][first_name]["properties"].pop(first_prop)

    result = compare_contract_with_live(model, live)
    assert not result["ok"]
    issues_text = "\n".join(result["issues"])
    assert f"字段缺失: {first_name}.{first_prop}" in issues_text, result["issues"]
    assert f"字段多余: {first_name}.renamed_{first_prop}" in issues_text, result["issues"]


def test_live_check_catches_missing_route_and_model():
    model = parse_contract(EXAMPLE)
    live = _live_doc_skeleton()
    # 删掉一条路由 + 一个 schema
    path = next(iter(live["paths"]))
    method = next(iter(live["paths"][path]))
    del live["paths"][path][method]
    schema_name = next(iter(live["components"]["schemas"]))
    del live["components"]["schemas"][schema_name]

    result = compare_contract_with_live(model, live)
    assert not result["ok"]
    issues_text = "\n".join(result["issues"])
    assert "路由缺失" in issues_text
    assert f"模型缺失: 运行时未导出 {schema_name}" in issues_text


def test_live_check_nested_class_schema_alias():
    """springdoc 嵌套类命名(Outer.Inner)应与契约模型名(Inner)对上,不误报缺失。"""
    model = parse_contract(EXAMPLE)
    live = _live_doc_skeleton()
    schema_name = next(iter(live["components"]["schemas"]))
    live["components"]["schemas"][f"FamilyDtos.{schema_name}"] = \
        live["components"]["schemas"].pop(schema_name)

    result = compare_contract_with_live(model, live)
    assert result["ok"], result["issues"]


def test_live_check_required_semantics():
    """required 语义:运行时未声明(空)默认视为未知不报;strict_required=True 时严格比对。"""
    model = parse_contract(EXAMPLE)
    live = _live_doc_skeleton()
    schema_name = next(iter(live["components"]["schemas"]))
    schema = live["components"]["schemas"][schema_name]
    if not schema.get("required"):
        return  # 契约无 required 字段,跳过
    schema["required"] = []
    # 默认(宽容):不报
    result = compare_contract_with_live(model, live)
    assert result["ok"], result["issues"]
    # 严格模式:报 required 不一致
    result = compare_contract_with_live(model, live, strict_required=True)
    assert not result["ok"]
    assert f"required 不一致: {schema_name}" in "\n".join(result["issues"])


def test_live_check_inline_enum_model():
    """契约独立枚举模型被运行时内联导出(springdoc 默认) → 不误报模型缺失。"""
    model = parse_contract(EXAMPLE)
    live = _live_doc_skeleton()
    # 找契约里的枚举 schema(petstore 可能没有,动态构造一个)
    enum_name = next((n for n, s in model["schemas"].items() if (s or {}).get("enum")), None)
    if enum_name is None:
        # 构造:契约加一个枚举模型,并在引用方属性里内联同样枚举(petstore 无枚举时)
        contract_model = dict(model)
        schemas = json.loads(json.dumps(model["schemas"]))  # 深拷贝
        schemas["Status"] = {"type": "string", "enum": ["A", "B"]}
        host = sorted(schemas)[0]
        schemas[host].setdefault("properties", {})["status"] = {"type": "string", "enum": ["A", "B"]}
        contract_model["schemas"] = schemas
        # 运行时:同名属性内联枚举,但不导出独立 Status schema
        live = _live_doc_skeleton()
        live_host = sorted(live["components"]["schemas"])[0]
        live["components"]["schemas"][live_host].setdefault("properties", {})["status"] = {
            "type": "string", "enum": ["A", "B"],
        }
        result = compare_contract_with_live(contract_model, live)
        assert result["ok"], result["issues"]
    else:
        # 契约真有枚举:从运行时 schemas 删除它,但把同样枚举内联到第一个属性里
        enum_values = [str(v) for v in model["schemas"][enum_name]["enum"]]
        live = _live_doc_skeleton()
        del live["components"]["schemas"][enum_name]
        host = next(iter(live["components"]["schemas"]))
        live["components"]["schemas"][host].setdefault("properties", {})["status"] = {
            "type": "string", "enum": enum_values,
        }
        result = compare_contract_with_live(model, live)
        assert result["ok"], result["issues"]


def main():
    test_live_check_pass_when_consistent()
    test_live_check_catches_serialization_drift()
    test_live_check_catches_missing_route_and_model()
    test_live_check_nested_class_schema_alias()
    test_live_check_required_semantics()
    test_live_check_inline_enum_model()
    print("OK: live_check 自测通过(6 组断言)")


if __name__ == "__main__":
    main()
