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


def main():
    test_manifest_coverage()
    test_cross_stack()
    test_drift_check()
    print("OK: consistency 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
