#!/usr/bin/env python3
"""OpenAPI 解析器自测。运行:python3 tests/test_parser.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.parser import parse_contract  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def test_parse():
    model = parse_contract(EXAMPLE)
    assert model["info"]["title"] == "Petstore"
    assert set(model["schemas"].keys()) == {"Pet", "CreatePet"}
    eps = {e["operation_id"]: e for e in model["endpoints"]}
    assert set(eps.keys()) == {"listPets", "createPet", "getPetById"}
    # 响应是数组
    assert eps["listPets"]["response_schema"]["type"] == "array"
    assert eps["listPets"]["response_schema"]["items"]["$ref"].endswith("/Pet")
    # 请求体是 $ref
    assert eps["createPet"]["request_schema"]["$ref"].endswith("/CreatePet")
    # 路径参数端点无请求体
    assert eps["getPetById"]["request_schema"] is None
    assert eps["getPetById"]["path"] == "/pets/{petId}"


def main():
    test_parse()
    print("OK: parser 自测通过")


if __name__ == "__main__":
    main()
