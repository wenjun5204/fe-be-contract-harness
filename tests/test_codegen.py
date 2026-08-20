#!/usr/bin/env python3
"""契约驱动生成 + G1 校验自测。运行:python3 tests/test_codegen.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.generator import generate  # noqa: E402
from lib.contract.verify import verify  # noqa: E402
from lib.stack.adapter import available  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def test_available_stacks():
    stacks = available()
    assert "react" in stacks and "node" in stacks, stacks


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


def test_verify_gate():
    for stack in ("react", "node"):
        r = verify(EXAMPLE, stack)
        assert r["ok"], r
        assert r["idempotent"], r
        assert r["routes_ok"] and r["models_ok"], r


def main():
    test_available_stacks()
    test_react_generate()
    test_node_generate()
    test_verify_gate()
    print("OK: codegen 自测通过(4 组断言)")


if __name__ == "__main__":
    main()
