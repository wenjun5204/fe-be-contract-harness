#!/usr/bin/env python3
"""契约一致性 + 漂移检测自测。运行:python3 tests/test_consistency.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.consistency import (  # noqa: E402
    check_manifest_coverage,
    cross_stack_check,
    drift_check,
)
from lib.contract.generator import write_out  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def test_manifest_coverage():
    routes = {"listPets", "createPet", "getPetById"}
    models = {"Pet", "CreatePet"}
    ok_r, ok_m = check_manifest_coverage({"routes": list(routes), "models": list(models)}, routes, models)
    assert ok_r and ok_m
    # 缺少一个 route → 检出不一致
    ok_r, ok_m = check_manifest_coverage({"routes": ["listPets"], "models": list(models)}, routes, models)
    assert not ok_r and ok_m


def test_cross_stack():
    r = cross_stack_check(EXAMPLE)
    assert r["ok"], r
    assert set(r["per_stack"].keys()) == {"react", "vue", "node", "java"}
    for s, v in r["per_stack"].items():
        assert v["routes_ok"] and v["models_ok"], (s, v)


def test_drift_check():
    with tempfile.TemporaryDirectory() as d:
        write_out(EXAMPLE, "node", d)
        r = drift_check(EXAMPLE, "node", d)
        assert r["ok"], r
        # 篡改 manifest → 检出漂移
        mp = Path(d) / "codegen-manifest.json"
        data = json.loads(mp.read_text(encoding="utf-8"))
        data["routes"] = ["only_one_route"]
        mp.write_text(json.dumps(data), encoding="utf-8")
        r = drift_check(EXAMPLE, "node", d)
        assert not r["ok"] and r["routes_drift"], r


def test_drift_writes_assumption_feedback():
    """E2 知识回流:真实漂移 → backend assumption 条目落库;无漂移/缺 manifest 不写。"""
    import lib.domain_knowledge as dk
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "kb"
        backup = dk.KB_DIR
        dk.KB_DIR = root  # 知识库根指到临时目录,不污染 config/
        try:
            write_out(EXAMPLE, "node", d)
            # 无漂移 → 不写
            r = drift_check(EXAMPLE, "node", d)
            assert r["ok"] and "knowledge_feedback" not in r, r
            # 真实漂移 → assumption 落库
            mp = Path(d) / "codegen-manifest.json"
            data = json.loads(mp.read_text(encoding="utf-8"))
            data["routes"] = ["only_one_route"]
            mp.write_text(json.dumps(data), encoding="utf-8")
            r = drift_check(EXAMPLE, "node", d)
            assert not r["ok"] and "已落库" in r["knowledge_feedback"], r
            entries = [e for e in dk.load_entries("backend", root)
                       if e["id"] == "drift-node-petstore"]
            assert entries and entries[0]["status"] == "assumption", entries
            assert entries[0]["source"] == "drift_check"
            assert "routes_drift=True" in entries[0]["content"]
            # 同 id 重复检出 → 幂等覆盖,不报错
            r = drift_check(EXAMPLE, "node", d)
            assert not r["ok"] and "已落库" in r["knowledge_feedback"], r
            assert len([e for e in dk.load_entries("backend", root)
                        if e["id"] == "drift-node-petstore"]) == 1
            # 缺 manifest → 不写回流(缺生成物不是知识,是噪音)
            mp.unlink()
            r = drift_check(EXAMPLE, "node", d)
            assert not r["ok"] and "缺少" in r.get("reason", ""), r
        finally:
            dk.KB_DIR = backup


def main():
    test_manifest_coverage()
    test_cross_stack()
    test_drift_check()
    test_drift_writes_assumption_feedback()
    print("OK: consistency 自测通过(4 组断言)")


if __name__ == "__main__":
    main()
