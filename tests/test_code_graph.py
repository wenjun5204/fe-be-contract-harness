#!/usr/bin/env python3
"""代码知识图自测。运行:python3 tests/test_code_graph.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.code_graph import build_index, find_definition, find_references, list_symbols, query  # noqa: E402


def test_index_and_query():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        (repo / "order.ts").write_text("export class Order { id: number }\nexport function createOrder() {}", encoding="utf-8")
        (repo / "use.ts").write_text("import { Order } from './order'\nconst o: Order = new Order()", encoding="utf-8")

        index = build_index(d)
        assert "Order" in list_symbols(index)
        assert "createOrder" in list_symbols(index)

        defs = find_definition(index, "Order")
        assert len(defs) == 1 and defs[0]["kind"] == "class", defs

        refs = find_references(index, "Order")
        assert "use.ts" in refs, refs

        r = query(index, "Order")
        assert r["risk"] in ("low", "medium"), r


def main():
    test_index_and_query()
    print("OK: code_graph 自测通过")


if __name__ == "__main__":
    main()
