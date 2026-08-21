#!/usr/bin/env python3
"""checkpoint 管理器自测。运行:python3 tests/test_checkpoint.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.checkpoint_manager import checkpoint_type, decide, requires_checkpoint  # noqa: E402


def test_requires():
    assert checkpoint_type("2") == "mandatory_review"
    assert requires_checkpoint("2")
    assert not requires_checkpoint("4")  # none


def test_mandatory_no_skip():
    r = decide("2", "approve")
    assert r["ok"] and r["decision"] == "approve", r
    r = decide("2", "skip")
    assert not r["ok"], r  # mandatory_review 不可跳过
    r = decide("2", "随便说说")
    assert r["ok"] and r["decision"] == "revise", r


def test_artifact_skip():
    r = decide("7", "skip")
    assert r["ok"] and r["decision"] == "skip", r


def main():
    test_requires()
    test_mandatory_no_skip()
    test_artifact_skip()
    print("OK: checkpoint 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
