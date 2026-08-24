#!/usr/bin/env python3
"""智能重试自测。运行:python3 tests/test_smart_retry.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.smart_retry import is_retryable, retry  # noqa: E402


def test_is_retryable():
    assert is_retryable(Exception("503 Service Unavailable"))
    assert is_retryable(Exception("Connection timed out"))
    assert not is_retryable(Exception("404 Not Found"))
    assert not is_retryable(Exception("SyntaxError"))


def test_retry_then_succeed():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("503 temporarily")
        return "ok"

    assert retry(flaky, retries=3, backoff=0) == "ok"
    assert calls["n"] == 3  # 失败 2 次后第 3 次成功


def test_permanent_fails_fast():
    calls = {"n": 0}

    def permanent():
        calls["n"] += 1
        raise RuntimeError("404 Not Found")

    try:
        retry(permanent, retries=3, backoff=0)
        assert False, "应抛错"
    except RuntimeError:
        pass
    assert calls["n"] == 1  # 永久错误不重试


def main():
    test_is_retryable()
    test_retry_then_succeed()
    test_permanent_fails_fast()
    print("OK: smart_retry 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
