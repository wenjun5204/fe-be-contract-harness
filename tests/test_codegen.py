#!/usr/bin/env python3
"""契约驱动生成 + G1 校验自测。运行:python3 tests/test_codegen.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.generator import generate  # noqa: E402
from lib.contract.verify import verify  # noqa: E402
from lib.stack.adapter import available  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def test_available_stacks():
    stacks = available()
    assert set(stacks) == {"react", "vue", "node", "java"}, stacks


def test_react_generate():
    files = generate(EXAMPLE, "react")
    assert "src/types/api.ts" in files
    assert "src/api/client.ts" in files
    assert "codegen-manifest.json" in files
    types = files["src/types/api.ts"]
    client = files["src/api/client.ts"]
    assert "interface Pet" in types
    assert "interface CreatePet" in types
    assert "listPets" in client and "createPet" in client and "getPetById" in client
    # 响应数组渲染为 Pet[]
    assert "Pet[]" in client
    # 路径参数进入函数签名
    assert "getPetById(petId: string)" in client
    # 类型导入路径正确(../types/api)
    assert "from '../types/api'" in client


def test_node_generate():
    files = generate(EXAMPLE, "node")
    assert "src/dto/Pet.dto.ts" in files
    assert "src/dto/CreatePet.dto.ts" in files
    assert "src/dto/index.ts" in files
    assert "src/controllers/pets.controller.ts" in files
    ctrl = files["src/controllers/pets.controller.ts"]
    assert "listPets" in ctrl and "createPet" in ctrl and "getPetById" in ctrl
    assert "Pet[]" in ctrl
    assert "@Post" in ctrl and "@Get" in ctrl
    # 路径参数路由 /:petId
    assert "@Get('/:petId')" in ctrl


def test_vue_generate():
    files = generate(EXAMPLE, "vue")
    assert "src/types/api.ts" in files
    assert "src/api/client.ts" in files
    assert "interface Pet" in files["src/types/api.ts"]
    assert "getPetById(petId: string)" in files["src/api/client.ts"]


def test_java_generate():
    files = generate(EXAMPLE, "java")
    assert "src/main/java/dto/Pet.java" in files
    assert "src/main/java/dto/CreatePet.java" in files
    assert "src/main/java/controller/PetsController.java" in files
    ctrl = files["src/main/java/controller/PetsController.java"]
    assert "listPets" in ctrl and "createPet" in ctrl and "getPetById" in ctrl
    assert "List<Pet>" in ctrl  # 数组 → List<Pet>
    assert "@PostMapping" in ctrl and "@GetMapping" in ctrl
    assert "private String name;" in files["src/main/java/dto/Pet.java"]


def test_verify_gate():
    for stack in ("react", "vue", "node", "java"):
        r = verify(EXAMPLE, stack)
        assert r["ok"], r


def test_no_json_response_endpoint():
    """无 2xx JSON 响应的端点(二进制回图/204):四栈一致渲染为 void,不崩溃。

    回归:java_type(None) 曾因 \"$ref\" in None 抛 TypeError,
    而其余三栈 ts_type(None) -> \"void\" 早有兜底。
    """
    contract = {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/img": {"get": {"responses": {"200": {"description": "binary",
                "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}}}},
            "/ping": {"get": {"responses": {"204": {"description": "no content"}}}},
        },
        "components": {"schemas": {}},
    }
    with tempfile.TemporaryDirectory() as d:
        cpath = Path(d) / "no-resp.json"
        cpath.write_text(json.dumps(contract), encoding="utf-8")
        for stack in ("react", "vue", "node", "java"):
            files = generate(cpath, stack)
            rendered = "\n".join(str(f) for f in files.values())
            assert "get_img" in rendered and "get_ping" in rendered, (stack, rendered)
            # G1 不因空响应崩
            r = verify(cpath, stack)
            assert r["ok"], (stack, r)
        assert r["idempotent"], r
        assert r["routes_ok"] and r["models_ok"], r


def main():
    test_available_stacks()
    test_react_generate()
    test_node_generate()
    test_vue_generate()
    test_java_generate()
    test_verify_gate()
    test_no_json_response_endpoint()
    print("OK: codegen 自测通过(7 组断言)")


if __name__ == "__main__":
    main()
