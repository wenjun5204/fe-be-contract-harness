#!/usr/bin/env python3
"""可行性验证自测。运行:python3 tests/test_feasibility.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.feasibility import check_feasibility  # noqa: E402


def test_feasibility():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        (repo / "order_service.py").write_text("class Order:\n    pass", encoding="utf-8")
        spec = {"contract_readiness": {"entities": [
            {"name": "Order"},
            {"name": "Payment"},
        ]}}
        r = check_feasibility(spec, d)
        statuses = {f["entity"]: f["status"] for f in r["findings"]}
        assert statuses["Order"] == "existing"
        assert statuses["Payment"] == "new"
        assert r["summary"] == {"new": 1, "existing": 1}
        assert r["ok"] is False  # 有同名实体 → 需确认复用/冲突


def main():
    test_feasibility()
    print("OK: feasibility 自测通过")


if __name__ == "__main__":
    main()
