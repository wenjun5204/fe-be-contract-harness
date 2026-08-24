#!/usr/bin/env python3
"""通知自测。运行:python3 tests/test_notifier.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.notifier import notify, stage_notify  # noqa: E402


def test_file_sink():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "notify.log"
        notify(f"file:{path}", "title", "content", "info")
        text = path.read_text(encoding="utf-8")
        assert "[INFO] title: content" in text


def test_callable_sink():
    captured = {}

    def sink(title, content, level):
        captured["title"] = title
        captured["content"] = content
        captured["level"] = level

    stage_notify("Stage 6", ["7", "8"], "7/12", sink=sink)
    assert captured["title"] == "stage-completed"
    assert "Stage 6" in captured["content"] and "7/12" in captured["content"]


def main():
    test_file_sink()
    test_callable_sink()
    print("OK: notifier 自测通过")


if __name__ == "__main__":
    main()
