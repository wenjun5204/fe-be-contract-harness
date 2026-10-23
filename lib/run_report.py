#!/usr/bin/env python3
"""Run 级观测报告(O2):聚合 events.jsonl + state.json → run 质量指标。

观测层三件套的"消费端":P0-5 埋了点(events.jsonl/transcripts),本模块把
埋点变成可看的指标,供交付复盘(E4)与外循环进化提供数据基础。

指标:
- 阶段层:执行耗时 / 审批等待 / 门控拦截次数 / resume_skip 次数
- 人工层:checkpoint revise 次数(返工指标)
- LLM 层:tool_call 总数 / turns / nudge 与 condenser 触发 / 失败数
- run 层:总耗时 / done 比例 / blocked 事件清单

用法:
    python3 lib/run_report.py --out <gen目录> --state <state.json>
    python3 lib/runner.py report --out gen --state state.json   (runner 子命令)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.state_manager import read_state  # noqa: E402


def _parse_iso(ts: Optional[str]):
    """ISO 8601 Z 字符串 → datetime;失败返回 None(观测尽力而为)。"""
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _load_events(out_dir: Optional[Path]) -> List[dict]:
    if not out_dir:
        return []
    f = Path(out_dir) / "events.jsonl"
    if not f.is_file():
        return []
    events = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 崩溃半截行容忍
    return events


def _llm_metrics(events: List[dict]) -> dict:
    """从 --live 事件(detail 含 transcript/tool_call_count)聚合 LLM 行为指标。"""
    stats = {"llm_stages": 0, "tool_calls": 0, "turns": 0, "nudges": 0,
             "condensed_events": 0, "retries": 0, "failed": 0, "succeeded": 0}
    for e in events:
        if e.get("kind") != "llm":
            continue
        d = e.get("detail") or {}
        stats["llm_stages"] += 1
        stats["tool_calls"] += d.get("tool_call_count") or 0
        transcript = d.get("transcript") or []
        stats["turns"] += len(transcript)
        for t in transcript:
            if t.get("nudged"):
                stats["nudges"] += 1
            if t.get("condensed"):
                stats["condensed_events"] += 1
            if t.get("retry"):
                stats["retries"] += t.get("retry")
        if d.get("ok"):
            stats["succeeded"] += 1
        else:
            stats["failed"] += 1
    return stats


def build_report(out_dir: Optional[str | Path], state_file: str | Path) -> dict:
    """聚合单次 run 的观测指标(尽力而为:缺哪块数据就少哪项,不报错)。"""
    events = _load_events(Path(out_dir) if out_dir else None)
    state = read_state(Path(state_file))
    stages = state["stages"]

    blocked = [e for e in events if e.get("kind") == "blocked"]
    resume_skips = [e for e in events if e.get("kind") == "resume_skip"]
    failed_events = [e for e in events if e.get("kind") == "failed"]
    revised = sum(
        1 for s in stages.values()
        for _ in [1] if (s.get("checkpoint") or {}).get("decision") == "revise"
    )

    durations = {
        sid: s.get("execution_seconds")
        for sid, s in stages.items()
        if s.get("execution_seconds") is not None
    }
    checkpoint_waits = {
        sid: s.get("checkpoint_wait_seconds")
        for sid, s in stages.items()
        if s.get("checkpoint_wait_seconds") is not None
    }

    done = sum(1 for s in stages.values() if s["state"] in ("completed", "skipped"))

    # ---- KPI 块(可量化收益) ----
    # 口径:
    # - success_rate: 终态阶段 / 总阶段(12/12 = 1.0;0.92 表示 11/12)
    # - human_interventions: checkpoint 人工 approve + revise + failed 事件(需人工 retry)
    # - total_duration: state created_at → 最后 updated_at 墙钟(含人工等待)
    # - requirement_scale: contract_stats(endpoints/schemas/fields),吞吐分母
    # - recovery_count: 有 error 记录但最终 completed 的阶段(失败后恢复)
    human_approves = sum(
        1 for s in stages.values()
        if (s.get("checkpoint") or {}).get("approved_by") == "user"
    )
    recovered = sum(
        1 for s in stages.values()
        if s.get("error") and s["state"] in ("completed", "skipped")
    )
    total = len(stages)
    started = _parse_iso(state.get("created_at"))
    last = max(
        (v.get("updated_at") or "" for v in stages.values()), default=""
    ) or state.get("updated_at")
    ended = _parse_iso(last)
    duration = round((ended - started).total_seconds(), 1) if (started and ended) else None

    kpi = {
        "success_rate": round(done / total, 3) if total else None,
        "failure_events": len(failed_events),
        "recovered_stages": recovered,
        "human_interventions": human_approves + revised + len(failed_events),
        "total_duration_seconds": duration,
        "requirement_scale": state.get("contract_stats"),
        "throughput": (
            round(state["contract_stats"]["endpoints"] / duration, 3)
            if duration and state.get("contract_stats") and duration > 0
            else None
        ),
    }

    return {
        "change_id": state.get("change_id"),
        "progress": f"{done}/{len(stages)}",
        "kpi": kpi,
        "stage": {
            "durations_seconds": durations,
            "checkpoint_wait_seconds": checkpoint_waits,
            "slowest": max(durations, key=durations.get) if durations else None,
            "gate_blocked_count": len(blocked),
            "gate_blocked_stages": sorted({e.get("stage") for e in blocked}),
            "resume_skip_stages": sorted({e.get("stage") for e in resume_skips}),
            "failed_events": len(failed_events),
        },
        "human": {"checkpoint_revises": revised},
        "llm": _llm_metrics(events),
        "events_total": len(events),
    }


METRICS_FILE = "metrics.jsonl"


def append_metrics(out_dir: str | Path, report: dict) -> Optional[Path]:
    """KPI 趋势埋点:每次 report 追加一行 metrics.jsonl(跨 run 基线/趋势)。

    append-only 与 events.jsonl 同模式;趋势消费(对比历史/画曲线)等积累后做。
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = json.dumps({
        "at": ts,
        "change_id": report.get("change_id"),
        "progress": report.get("progress"),
        "kpi": report.get("kpi"),
    }, ensure_ascii=False, default=str)
    path = Path(out_dir) / METRICS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="run 观测报告:聚合 events/state 为指标")
    p.add_argument("--out", default="gen", help="生成目录(events.jsonl 所在)")
    p.add_argument("--state", default="state.json")
    p.add_argument("--no-metrics", action="store_true",
                   help="只打印报告,不追加 metrics.jsonl 趋势")
    args = p.parse_args(argv)
    report = build_report(args.out, args.state)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.no_metrics:
        append_metrics(args.out, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
