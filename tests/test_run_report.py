#!/usr/bin/env python3
"""run 观测报告(O2)自测:聚合 events/state 为指标。运行:python3 tests/test_run_report.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.run_report import build_report  # noqa: E402
from lib.runner import run  # noqa: E402
from lib.state_manager import summary  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def test_report_after_auto_run():
    """跑一次真实 --auto run 后,report 输出阶段耗时/进度/事件计数,summary 含耗时。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        r = run(EXAMPLE, out, state, ["node", "react"], auto=True)
        assert r["ok"], r

        # O1: summary 带 stage_durations——确定性阶段(0/5A/5B/6/10)有耗时;
        # skip 的 LLM 阶段不走 start,无 started_at,合理地不出现在耗时表
        s = summary(state)
        assert set(s["stage_durations"]) == {"0", "5A", "5B", "6", "10"}, s["stage_durations"]
        assert all(v >= 0 for v in s["stage_durations"].values())

        # O2: report 聚合
        report = build_report(out, state)
        assert report["progress"] == "12/12", report
        assert report["stage"]["durations_seconds"], report
        assert report["stage"]["slowest"] is not None, report  # 阶段 id 是字符串,可能为 "0"
        # events.jsonl 全量进入
        assert report["events_total"] == len(r["events"]), report
        # --auto 无 blocked(全 approve)
        assert report["stage"]["gate_blocked_count"] == 0, report
        # --auto 模式 LLM 阶段未真实执行 → llm 指标全零
        assert report["llm"]["llm_stages"] == 0, report["llm"]
        # 快速重跑产生 resume_skip → report 可见
        run(EXAMPLE, out, state, ["node", "react"], auto=True)
        report2 = build_report(out, state)
        assert set(report2["stage"]["resume_skip_stages"]) >= {"5A", "5B"}, report2


def test_report_degrades_gracefully():
    """无 events.jsonl 时 report 仍可输出(降级不报错)。"""
    with tempfile.TemporaryDirectory() as d:
        state = Path(d) / "state.json"
        from lib.state_manager import init_state
        init_state(state, "empty")
        report = build_report(Path(d) / "nonexistent-out", state)
        assert report["progress"] == "0/12", report
        assert report["events_total"] == 0
        assert report["llm"]["llm_stages"] == 0


def test_kpi_block_and_metrics_trend():
    """KPI 六项指标口径 + contract_stats 落 state + metrics.jsonl 趋势追加。"""
    import json

    from lib.run_report import append_metrics
    from lib.state_manager import read_state
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        run(EXAMPLE, out, state, ["node"], auto=True)

        # contract_stats 落 state(需求规模 = 吞吐分母)
        st = read_state(state)
        cs = st["contract_stats"]
        assert cs["endpoints"] == 3 and cs["schemas"] == 2, cs  # petstore: 3 路由 2 模型
        assert cs["fields"] > 0, cs
        # 重跑不覆盖首次口径
        run(EXAMPLE, out, state, ["node"], auto=True)
        assert read_state(state)["contract_stats"] == cs

        # KPI 块
        report = build_report(out, state)
        kpi = report["kpi"]
        assert kpi["success_rate"] == 1.0, kpi           # 12/12 终态
        assert kpi["failure_events"] == 0, kpi
        assert kpi["recovered_stages"] == 0, kpi
        assert kpi["human_interventions"] == 0, kpi       # --auto 全自动,零人工
        assert kpi["total_duration_seconds"] is not None and kpi["total_duration_seconds"] >= 0, kpi
        assert kpi["requirement_scale"] == cs, kpi
        # throughput = endpoints/秒;亚秒级 run(演示场景)duration 截断为 0 → None,
        # 真实 run(秒级以上)才有意义
        if kpi["total_duration_seconds"] and kpi["total_duration_seconds"] > 0:
            assert kpi["throughput"] is not None and kpi["throughput"] > 0, kpi
        else:
            assert kpi["throughput"] is None, kpi

        # metrics.jsonl 趋势:两次 report 两次追加,含 change_id 与 kpi
        append_metrics(out, report)
        append_metrics(out, report)
        lines = [json.loads(x) for x in (out / "metrics.jsonl").read_text().splitlines()]
        assert len(lines) == 2 and all(ln["change_id"] and "kpi" in ln for ln in lines), lines
        assert lines[0]["kpi"]["success_rate"] == 1.0, lines[0]


def main():
    test_report_after_auto_run()
    test_report_degrades_gracefully()
    test_kpi_block_and_metrics_trend()
    print("OK: run_report 自测通过(3 组断言)")


if __name__ == "__main__":
    main()
