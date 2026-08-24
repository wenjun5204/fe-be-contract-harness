#!/usr/bin/env python3
"""波次调度自测。运行:python3 tests/test_parallel_wave_scheduler.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.parallel_wave_scheduler import run, schedule  # noqa: E402


def test_schedule_topology():
    tasks = {
        "5A": [], "5B": [],
        "6": ["5A", "5B"],
        "7": ["6"], "8": ["6"],
        "9": ["7", "8"],
    }
    waves = schedule(tasks)
    # 5A/5B 第一波(并行),6 第二波,7/8 第三波,9 第四波
    assert waves[0] == ["5A", "5B"], waves
    assert waves[1] == ["6"], waves
    assert waves[2] == ["7", "8"], waves
    assert waves[3] == ["9"], waves


def test_cycle_detection():
    try:
        schedule({"a": ["b"], "b": ["a"]})
        assert False, "应抛循环依赖"
    except ValueError:
        pass


def test_run():
    tasks = {"5A": [], "5B": [], "6": ["5A", "5B"]}
    results = run(tasks, lambda t: f"done:{t}")
    assert results == {"5A": "done:5A", "5B": "done:5B", "6": "done:6"}, results


def main():
    test_schedule_topology()
    test_cycle_detection()
    test_run()
    print("OK: parallel_wave_scheduler 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
