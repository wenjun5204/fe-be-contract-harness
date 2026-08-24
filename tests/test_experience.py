#!/usr/bin/env python3
"""经验沉淀自测。运行:python3 tests/test_experience.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.experience import load, log, query  # noqa: E402


def test_log_and_query():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        log("review", "契约漂移常见:字段类型不一致导致一致性校验失败", "code-review", root)
        log("error", "OpenAPI allOf 不支持,已记录", "parser", root)

        hits = query("契约漂移", root=root)
        assert hits and hits[0]["category"] == "review", hits

        assert "allOf" in load("error", root)
        # 跨分类不串
        assert "allOf" not in load("review", root)


def main():
    test_log_and_query()
    print("OK: experience 自测通过")


if __name__ == "__main__":
    main()
