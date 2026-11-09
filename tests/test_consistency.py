#!/usr/bin/env python3
"""契约一致性 + 漂移检测自测。运行:python3 tests/test_consistency.py"""
import contextlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lib.domain_knowledge as dk  # noqa: E402
from lib.contract.consistency import (  # noqa: E402
    check_manifest_coverage,
    cross_stack_check,
    drift_check,
)
from lib.contract.generator import write_out  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


@contextlib.contextmanager
def _isolated_kb(tmpdir):
    """E2 回流副作用隔离:知识库根指到临时目录,不污染 config/domain-knowledge/。

    drift_check 检出真实漂移会自动写 backend assumption(E2 知识回流)——
    任何触发漂移的测试都必须套本隔离(与 E1 采集池隔离同规,真实首跑发现 #5)。
    """
    backup = dk.KB_DIR
    dk.KB_DIR = Path(tmpdir) / "kb"
    try:
        yield
    finally:
        dk.KB_DIR = backup


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
    assert set(r["per_stack"].keys()) == {"react", "vue", "react_native", "expo", "node", "java"}
    for s, v in r["per_stack"].items():
        assert v["routes_ok"] and v["models_ok"], (s, v)


def test_drift_check():
    # 触发真实漂移 → E2 回流会写知识库,必须隔离(不污染 config/)
    with tempfile.TemporaryDirectory() as d, _isolated_kb(d):
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
    """E2 知识回流:真实漂移 → backend assumption 条目按产品作用域落库;
    无漂移/缺 manifest 不写。方案 B:product 归位 products/<pid>/,
    无 product → pending/ 兜底(绝不落 _global/)。"""
    with tempfile.TemporaryDirectory() as d, _isolated_kb(d):
        write_out(EXAMPLE, "node", d)
        # 无漂移 → 不写
        r = drift_check(EXAMPLE, "node", d, product="petstore")
        assert r["ok"] and "knowledge_feedback" not in r, r
        # 真实漂移 → assumption 落库(products/petstore/)
        mp = Path(d) / "codegen-manifest.json"
        data = json.loads(mp.read_text(encoding="utf-8"))
        data["routes"] = ["only_one_route"]
        mp.write_text(json.dumps(data), encoding="utf-8")
        r = drift_check(EXAMPLE, "node", d, product="petstore")
        assert not r["ok"] and "products/petstore" in r["knowledge_feedback"], r
        entries = [e for e in dk.load_entries("backend", dk.KB_DIR, product="petstore")
                   if e["id"] == "drift-node-petstore"]
        assert entries and entries[0]["status"] == "assumption", entries
        assert entries[0]["source"] == "drift_check"
        assert entries[0]["scope"] == "product"
        assert "routes_drift=True" in entries[0]["content"]
        # 其他产品读不到这条漂移知识(隔离)
        assert not [e for e in dk.load_entries("backend", dk.KB_DIR, product="other")
                    if e["id"] == "drift-node-petstore"]
        # 同 id 重复检出 → 幂等覆盖,不报错
        r = drift_check(EXAMPLE, "node", d, product="petstore")
        assert not r["ok"] and "已落库" in r["knowledge_feedback"], r
        assert len([e for e in dk.load_entries("backend", dk.KB_DIR, product="petstore")
                    if e["id"] == "drift-node-petstore"]) == 1
        # 缺 manifest → 不写回流(缺生成物不是知识,是噪音)
        mp.unlink()
        r = drift_check(EXAMPLE, "node", d, product="petstore")
        assert not r["ok"] and "缺少" in r.get("reason", ""), r


def test_drift_without_product_lands_in_pending():
    """写侧 fail-closed:product 无法解析 → pending/ 兜底 + warning,绝不落 _global/。"""
    with tempfile.TemporaryDirectory() as d, _isolated_kb(d):
        write_out(EXAMPLE, "node", d)
        mp = Path(d) / "codegen-manifest.json"
        data = json.loads(mp.read_text(encoding="utf-8"))
        data["routes"] = ["only_one_route"]
        mp.write_text(json.dumps(data), encoding="utf-8")
        r = drift_check(EXAMPLE, "node", d)
        assert not r["ok"] and "pending" in r["knowledge_feedback"], r
        assert "product 未解析" in r["knowledge_feedback"], r
        # 落在 pending/(悬置待人工归位),任何产品读侧都看不到
        assert (dk.KB_DIR / "pending" / "backend" / "drift-node-petstore.md").is_file()
        assert not dk.load_entries("backend", dk.KB_DIR)
        assert not (dk.KB_DIR / "_global" / "backend").exists() or not any(
            (dk.KB_DIR / "_global" / "backend").glob("drift-*.md")), "漂移知识绝不能落 _global/"
        # 人工 confirm 可将其显式升级迁移(to_global)
        res = dk.confirm_entry("backend", "drift-node-petstore", "liuwenjun05", dk.KB_DIR, to_global=True)
        assert res["scope"] == "global", res
        assert not (dk.KB_DIR / "pending" / "backend" / "drift-node-petstore.md").exists()


def main():
    test_manifest_coverage()
    test_cross_stack()
    test_drift_check()
    test_drift_writes_assumption_feedback()
    test_drift_without_product_lands_in_pending()
    print("OK: consistency 自测通过(5 组断言)")


if __name__ == "__main__":
    main()
