#!/usr/bin/env python3
"""智能重试:指数退避 + 瞬时/永久错误区分(对齐 super-assistant smart_retry)。"""
from __future__ import annotations

import time
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

# 瞬时错误关键词(可重试):超时 / 限流 / 服务暂不可用
RETRYABLE_KEYWORDS = ("timeout", "429", "503", "502", "connection", "temporarily", "timed out", "retry")


def is_retryable(error: Exception) -> bool:
    msg = str(error).lower()
    return any(k in msg for k in RETRYABLE_KEYWORDS)


def retry(
    fn: Callable[[], T],
    retries: int = 3,
    backoff: float = 2.0,
    retryable: Optional[Callable[[Exception], bool]] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> T:
    """指数退避重试。retryable 判定是否重试(默认 is_retryable),永久错误不重试直接抛。"""
    check = retryable or is_retryable
    last: Exception = Exception("unreachable")
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            if attempt == retries or not check(e):
                raise
            if on_retry:
                on_retry(attempt + 1, e)
            time.sleep(backoff ** attempt)
    raise last


if __name__ == "__main__":
    import sys
    # 演示:永久错误(404)不重试,瞬时错误(503)重试
    def boom():
        raise RuntimeError("503 Service Unavailable")
    try:
        retry(boom, retries=2, backoff=0)
    except RuntimeError as e:
        print(f"最终失败(重试后): {e}")
        sys.exit(0)
