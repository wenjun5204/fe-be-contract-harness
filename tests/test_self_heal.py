#!/usr/bin/env python3
"""依赖自愈自测。运行:python3 tests/test_self_heal.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.self_heal import detect, heal  # noqa: E402


def test_detect_returns_list():
    missing = detect()
    assert isinstance(missing, list)
    # 每个缺失项有 name/install/critical 字段
    for m in missing:
        assert "name" in m and "install" in m and "critical" in m


def test_heal():
    r = heal(auto_install=False)  # 不安装,只检测
    assert "ok" in r and "missing" in r and "suggestion" in r


def main():
    test_detect_returns_list()
    test_heal()
    print("OK: self_heal 自测通过")


if __name__ == "__main__":
    main()
