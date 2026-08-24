#!/usr/bin/env python3
"""并行波次调度器:把任务按依赖拓扑分层,每波内并行(对齐 super-assistant parallel_wave_scheduler)。

典型用例:Stage 5A/5B 前后端实现并行(同波),Stage 6 一致性校验依赖两者(下一波)。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List


def schedule(tasks: Dict[str, List[str]]) -> List[List[str]]:
    """tasks: {task_id: [依赖 task_id]}。返回波次列表(拓扑分层,Kahn 算法)。

    - 无依赖的任务在第一波
    - 依赖满足后在下一波
    - 检测循环依赖
    """
    indegree = {t: len(deps) for t, deps in tasks.items()}
    dependents: Dict[str, List[str]] = {t: [] for t in tasks}
    for t, deps in tasks.items():
        for d in deps:
            if d not in tasks:
                raise ValueError(f"依赖 {d} 不在任务列表中({t} 依赖它)")
            dependents.setdefault(d, []).append(t)

    ready = sorted(t for t in tasks if indegree[t] == 0)
    waves: List[List[str]] = []
    while ready:
        waves.append(ready)
        nxt = []
        for t in ready:
            for dep in dependents.get(t, []):
                indegree[dep] -= 1
                if indegree[dep] == 0:
                    nxt.append(dep)
        ready = sorted(nxt)

    if sum(len(w) for w in waves) != len(tasks):
        raise ValueError("任务图存在循环依赖")
    return waves


def run(tasks: Dict[str, List[str]], executor: Callable[[str], object], max_workers: int = 4) -> Dict[str, object]:
    """按波次执行,每波内并行。executor(task_id) -> 结果。"""
    waves = schedule(tasks)
    results: Dict[str, object] = {}
    for wave in waves:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {t: pool.submit(executor, t) for t in wave}
            for t, fut in futures.items():
                results[t] = fut.result()
    return results


if __name__ == "__main__":
    import json
    # 演示:5A/5B 并行,6 依赖两者,7/8 依赖 6,9 依赖 7+8
    tasks = {
        "5A": [], "5B": [],
        "6": ["5A", "5B"],
        "7": ["6"], "8": ["6"],
        "9": ["7", "8"],
    }
    print(json.dumps(schedule(tasks), ensure_ascii=False, indent=2))
