#!/usr/bin/env python3
"""仓库知识提取自测。运行:python3 tests/test_repo_knowledge.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.repo_knowledge import build_knowledge, detect_stack, save  # noqa: E402


def test_detect_and_build():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        (repo / "package.json").write_text('{"dependencies": {"react": "^18"}}', encoding="utf-8")
        (repo / "src").mkdir()
        (repo / "src" / "App.tsx").write_text("export default function App() {}", encoding="utf-8")

        stacks = detect_stack(d)
        assert stacks["react"] is True, stacks

        kb = build_knowledge(d)
        assert "react" in kb
        assert "package.json" in kb
        assert "src/App.tsx" in kb or "src" in kb


def test_save():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        (repo / "package.json").write_text("{}", encoding="utf-8")
        out = save(d, Path(d) / "kb")
        assert out.exists()
        assert "# 仓库知识" in out.read_text(encoding="utf-8")


def main():
    test_detect_and_build()
    test_save()
    print("OK: repo_knowledge 自测通过(2 组断言)")


if __name__ == "__main__":
    main()
