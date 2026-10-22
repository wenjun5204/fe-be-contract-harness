#!/usr/bin/env python3
"""评测集:契约 → 期望产物 的回归基准(规则重放)。

每个 case = 一个契约 + 一个 expected.json。评测项:
1. 解析契约,routes/models 与期望一致
2. 各栈 codegen + G1 生成门通过,产物 hash 完整(manifest.artifacts 齐全)
3. 可选 expected.response_types:空响应端点四栈渲染 void(P2-6 回归 java_type(None) 修复)
4. 可选 expected.cross_stack_consistent:跨栈一致性报告 ok
运行:python3 evals/run_evals.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.consistency import cross_stack_check  # noqa: E402
from lib.contract.generator import generate, write_out  # noqa: E402
from lib.contract.parser import parse_contract  # noqa: E402
from lib.contract.verify import verify  # noqa: E402

CASES_DIR = Path(__file__).resolve().parent / "cases"


def _rendered_types(contract: Path, stack: str) -> dict:
    """从生成产物粗提取端点返回类型渲染(frontend: Promise<X>;java: public X)。"""
    files = generate(contract, stack)
    import re
    rendered = {}
    all_routes = {e["operation_id"] for e in parse_contract(contract)["endpoints"]}
    for content in files.values():
        for opid in all_routes:
            if opid in rendered:
                continue
            m = re.search(rf"{opid}\((?:[^)]*)\)\s*:\s*Promise<(\w+)>", content) \
                or re.search(rf"public\s+(\w+)\s+{opid}\(", content)
            if m:
                rendered[opid] = m.group(1)
    return rendered


def run_case(name: str) -> dict:
    contract = CASES_DIR / f"{name}.yaml"
    expected = json.loads((CASES_DIR / f"{name}.expected.json").read_text(encoding="utf-8"))

    model = parse_contract(contract)
    routes = {e["operation_id"] for e in model["endpoints"]}
    models = set(model["schemas"].keys())

    routes_ok = routes == set(expected["routes"])
    models_ok = models == set(expected["models"])

    gates, hash_ok = {}, {}
    with tempfile.TemporaryDirectory() as d:
        for s in expected["stacks"]:
            gates[s] = verify(contract, s)["ok"]
            write_out(contract, s, Path(d) / s)  # 落盘,验证 manifest.artifacts hash 完整
            manifest = json.loads((Path(d) / s / "codegen-manifest.json").read_text(encoding="utf-8"))
            hash_ok[s] = bool(manifest.get("artifacts"))

    # 可选:void_routes —— 无 2xx JSON 响应的端点四栈必须渲染 void
    types_ok = True
    void_routes = expected.get("void_routes")
    if void_routes:
        for s in ("react", "vue", "java"):
            actual = _rendered_types(contract, s)
            for opid in void_routes:
                if actual.get(opid) != "void":
                    types_ok = False

    # 可选:跨栈一致性
    consistency_ok = True
    if expected.get("cross_stack_consistent"):
        consistency_ok = cross_stack_check(contract).get("ok", False)

    return {
        "case": name,
        "ok": routes_ok and models_ok and all(gates.values()) and all(hash_ok.values())
             and types_ok and consistency_ok,
        "routes_ok": routes_ok,
        "models_ok": models_ok,
        "gates": gates,
        "hash_ok": hash_ok,
        "types_ok": types_ok,
        "consistency_ok": consistency_ok,
    }


def main(argv=None) -> int:
    cases = [p.stem for p in CASES_DIR.glob("*.yaml")]
    results = [run_case(c) for c in sorted(cases)]
    for r in results:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    ok = all(r["ok"] for r in results)
    print(f"eval: {sum(1 for r in results if r['ok'])}/{len(results)} passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
