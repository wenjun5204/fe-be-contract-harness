#!/usr/bin/env python3
"""通知 sink 抽象:阶段进度通知(非阻塞)。本地 fallback:stderr / file;可扩展到大象 IM。

对齐 super-assistant daxiang-notifier(非阻塞阶段通知)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Union

Sink = Union[str, Callable[[str, str, str], None]]


def notify(sink: Sink, title: str, content: str, level: str = "info") -> None:
    """sink:
    - callable(title, content, level) → 自定义通道
    - 'stderr' → 打印到 stderr(默认)
    - 'file:<path>' → 追加到文件
    """
    if callable(sink):
        sink(title, content, level)
        return
    if isinstance(sink, str) and sink.startswith("file:"):
        path = Path(sink[5:])
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{level.upper()}] {title}: {content}\n")
        return
    import sys
    print(f"[{level.upper()}] {title}: {content}", file=sys.stderr)


def stage_notify(
    stage_name: str,
    next_stages: list,
    progress: str,
    sink: Sink = "stderr",
) -> None:
    """阶段完成通知(非阻塞):已完成阶段 + 下一步 + 进度。"""
    content = f"阶段完成: {stage_name} → 下一步: {', '.join(next_stages) or '无'} | 进度: {progress}"
    notify(sink, "stage-completed", content, "info")


if __name__ == "__main__":
    stage_notify("Stage 6 一致性校验", ["7", "8"], "7/12", sink="stderr")
