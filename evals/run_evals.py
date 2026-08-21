#!/usr/bin/env python3
"""最小评测集:契约 → 期望产物 的回归基准。

每个 case = 一个契约 + 一个 expected.json(routes/models/stacks)。
评测项:
1. 解析契约,routes/models 与期望一致
2. 各栈 codegen + G1 生成门通过
运行:python3 evals/run_evals.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contract.generator import generate  # noqa: E402
from lib.contract.parser import parse_contract  # noqa: E402
from lib.contract.verify import verify  # noqa: E402

CASES_DIR = Path(__file__).resolve().parent / "cases"


def run_case(name: str) -> dict:
    contract = CASES_DIR / f"{name}.yaml"
    expected = json.loads((CASES_DIR / f"{name}.expected.json").read_text(encoding="utf-8"))

    model = parse_contract(contract)
    routes = {e["operation_id"] for e in model["endpoints"]}
    models = set(model["schemas"].keys())

    routes_ok = routes == set(expected["routes"])
    models_ok = models == set(expected["models"])

    gates = {}
    for s in expected["stacks"]:
        gates[s] = verify(contract, s)["ok"]
        generate(contract, s)  # 确保可生成

    return {
        "case": name,
        "ok": routes_ok and models_ok and all(gates.values()),
        "routes_ok": routes_ok,
        "models_ok": models_ok,
        "gates": gates,
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
