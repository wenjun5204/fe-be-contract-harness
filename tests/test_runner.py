#!/usr/bin/env python3
"""runner 自测(第一阶段):确定性阶段经 transition 完成,LLM 阶段只签发指令,不可绕过。

运行:python3 tests/test_runner.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.runner import run  # noqa: E402
from lib.state_manager import read_state  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def test_auto_mode_completes_loop():
    """--auto:LLM 阶段显式带批准跳过,checkpoint 自动 approve,全部阶段终态,产物落盘。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        r = run(EXAMPLE, out, state, ["node", "react"], auto=True)
        assert r["ok"], r
        # 12 阶段全部终态(completed/skipped)
        assert r["summary"]["done"] == 12, r["summary"]
        assert not r["summary"]["running"] and not r["summary"]["failed"]
        # codegen 产物真实落盘
        assert (out / "node" / "codegen-manifest.json").exists()
        assert (out / "react" / "codegen-manifest.json").exists()
        # 终态全部带审计字段(receipt / completed_at / evidence)
        st = read_state(state)["stages"]
        for sid, s in st.items():
            assert s["state"] in ("completed", "skipped"), (sid, s)
            assert s["completed_at"], (sid, s)
            if s["state"] == "completed":
                assert s["receipt"], (sid, s)
        # 无 blocked 事件
        assert not [e for e in r["events"] if e["kind"] == "blocked"], r["events"]
        # 状态文件可续跑
        assert state.exists()
        # P0-5: 事件溯源落盘——events.jsonl 每条一行,行数与内存事件一致,均含时间戳
        events_file = out / "events.jsonl"
        assert events_file.exists(), "events.jsonl 应随 run 落盘"
        lines = [json.loads(x) for x in events_file.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(lines) == len(r["events"]), (len(lines), len(r["events"]))
        assert all(ln["at"] and ln["change_id"] for ln in lines), lines[0]


def test_java_vue_receipts_match_actual_codegen_agents():
    """Java + Vue 时，5A/5B receipt 必须记录对应实际 codegen Agent。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        r = run(EXAMPLE, out, state, ["java", "vue"], auto=True)
        assert r["ok"], r
        st = read_state(state)["stages"]
        assert st["5A"]["receipt"]["subagent"] == "codegen/java-codegen", st["5A"]
        assert st["5B"]["receipt"]["subagent"] == "codegen/vue-codegen", st["5B"]
        assert (out / "java" / "codegen-manifest.json").exists()
        assert (out / "vue" / "codegen-manifest.json").exists()


def test_non_auto_directives_include_budgeted_knowledge_context():
    """非 auto 派发指令应携带由契约实体、仓库文档和预算共同约束的上下文。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        repo = root / "repo"
        docs = repo / ".agents" / "docs"
        docs.mkdir(parents=True)
        (docs / "architecture.md").write_text("ARCH", encoding="utf-8")
        (docs / "conventions.md").write_text("CONV", encoding="utf-8")
        (docs / "domain-model.md").write_text("MODEL", encoding="utf-8")
        r = run(EXAMPLE, root / "gen", root / "state.json", ["node", "react"], auto=False, repo=repo, context_max_tokens=1000)
        directives = {event["stage"]: event["detail"] for event in r["events"] if event["kind"] == "agent"}
        stage_two = directives["2"]
        assert stage_two["context"]["schema"] == "dispatch-context/v1"
        assert "Pet" in stage_two["context"]["entities"]
        assert "CONV" in stage_two["context"]["text"]
        assert stage_two["context"]["estimated_tokens"] <= 1000


def test_non_auto_blocks_at_unmet_prereq():
    """非 auto:LLM 阶段仅签发指令;前置未就绪的确定性阶段被 transition 真实阻断。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        r = run(EXAMPLE, out, state, ["node", "react"], auto=False)
        assert r["ok"], r
        # 仅 Stage 0 终态;LLM 阶段(1/2/3/4/7/8/9)签发指令
        assert r["summary"]["done"] == 1, r["summary"]
        agent_stages = {e["stage"] for e in r["events"] if e["kind"] == "agent"}
        assert agent_stages == {"1", "2", "3", "4", "7", "8", "9"}, agent_stages
        # 前置未就绪的推进被阻断(不可绕过)
        blocked = [e["stage"] for e in r["events"] if e["kind"] == "blocked"]
        assert "5A" in blocked and "5B" in blocked and "6" in blocked, blocked
        # 当前可推进:仅 Stage 1(等待需求分析)
        assert r["next_actionable"] == ["1"], r["next_actionable"]
        # 状态机一致:stage 0 completed,其余非终态
        st = read_state(state)["stages"]
        assert st["0"]["state"] == "completed"
        assert st["1"]["state"] == "pending"


def test_rerun_is_idempotent_resume():
    """P0-2: 已终态 codegen 阶段重跑不重写文件(resume_skip),产物 mtime 不变。"""
    import os
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        run(EXAMPLE, out, state, ["node"], auto=True)
        manifest = out / "node" / "codegen-manifest.json"
        mtime_before = os.stat(manifest).st_mtime_ns
        r = run(EXAMPLE, out, state, ["node"], auto=True)
        # 5A 被识别为已终态 → resume_skip,不再走 codegen/transition
        skips = [e for e in r["events"] if e["kind"] == "resume_skip"]
        assert {e["stage"] for e in skips} >= {"5A"}, skips
        # 文件未被重写
        assert os.stat(manifest).st_mtime_ns == mtime_before, "重跑不应重写已终态阶段的生成文件"
        # 12 阶段仍全部终态
        assert r["summary"]["done"] == 12, r["summary"]


def test_parallel_wave_codegen_thread_safe():
    """P1-6: 5A/5B 波次并行,receipt 登记与 transition 串行化,两阶段都真实终态。"""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        # 前后端都有栈 → 5A/5B 同波并行执行
        r = run(EXAMPLE, out, state, ["node", "java", "react", "vue"], auto=True)
        assert r["ok"], r
        assert r["summary"]["done"] == 12, r["summary"]
        st = read_state(state)["stages"]
        assert st["5A"]["state"] == "completed" and st["5B"]["state"] == "completed", (st["5A"], st["5B"])
        # 两阶段的 receipt 均已消费(登记未被并发写覆盖)
        receipts = read_state(state)["receipts"]
        assert receipts["5A"]["used"] and receipts["5B"]["used"], receipts
        # 无 blocked(并行下 5A receipt 丢失会导致 gate_blocked)
        assert not [e for e in r["events"] if e["kind"] == "blocked"], [
            e for e in r["events"] if e["kind"] == "blocked"]


def test_live_auto_mock_partial_script_degrades_to_skip():
    """--live + --auto:mock 脚本未覆盖的 LLM 阶段降级为 auto skip(真实首跑发现 #1)。

    mock 演练可只覆盖感兴趣的阶段(此处仅 Stage 4):覆盖的阶段经 tool calling
    主循环真实过门完成,未覆盖的阶段显式跳过并注明降级原因,不要求脚本覆盖
    全部 9 个 LLM 阶段。
    """
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        script = Path(d) / "script.json"
        script.write_text(json.dumps({"stages": {"4": [
            {"tool_calls": [{"name": "report_outputs",
                             "arguments": {"outputs": {"branch_name": "feat/partial-drill"}}}]},
        ]}}, ensure_ascii=False), encoding="utf-8")
        r = run(EXAMPLE, out, state, ["node"], auto=True, live=True,
                llm_runtime="mock", llm_script=script)
        assert r["ok"], r
        # 12 阶段全部终态;被覆盖的 Stage 4 经真实执行完成,其余 LLM 阶段降级跳过
        assert r["summary"]["done"] == 12, r["summary"]
        assert not r["summary"]["failed"], r["summary"]
        st = read_state(state)["stages"]
        assert st["4"]["state"] == "completed", st["4"]
        assert st["4"]["outputs"]["branch_name"] == "feat/partial-drill", st["4"]
        assert read_state(state)["receipts"]["4"]["used"], st["4"]
        for sid in ("1", "2", "3", "7", "8", "9"):
            assert st[sid]["state"] == "skipped", (sid, st[sid])
        # 降级原因落事件(skip 事件 detail 注明降级,审计可见)
        skips = {e["stage"]: e["detail"] for e in r["events"] if e["kind"] == "skip"}
        for sid in ("1", "2", "3", "7", "8", "9"):
            assert "降级 auto 跳过" in skips[sid], (sid, skips)
        assert "4" not in skips, skips
        # Stage 4 走的是真实 llm 主循环,非 skip
        llm_events = [e for e in r["events"] if e["kind"] == "llm"]
        assert {e["stage"] for e in llm_events} == {"4"}, llm_events
        assert llm_events[0]["detail"]["ok"], llm_events[0]["detail"]
        # 无 blocked / failed 事件
        assert not [e for e in r["events"] if e["kind"] == "blocked"], r["events"]


def test_execution_plan_from_dag():
    """工作流解耦:执行计划由 workflow-dag.json 数据驱动(Kahn 拓扑分层)。

    - 全 12 阶段进计划,无遗漏无重复
    - 5A/5B 同波(impl 并行组),7/8 同波(delivery 并行组——旧 runner 顺序跑的缺口)
    - 汇合点 6/9 在其全部前置之后
    - parallel_groups 声明与分层矛盾时启动即报
    """
    from lib.runner import build_execution_plan
    from lib.state_manager import load_dag

    plan = build_execution_plan()
    flat = [sid for wave in plan for sid in wave]
    assert len(flat) == len(set(flat)) == 12, flat
    wave_of = {sid: i for i, wave in enumerate(plan) for sid in wave}
    assert wave_of["5A"] == wave_of["5B"], plan
    assert wave_of["7"] == wave_of["8"], plan               # delivery 组生效
    assert wave_of["5A"] < wave_of["6"] < wave_of["7"]       # 汇合点后置
    assert wave_of["7"] < wave_of["9"] < wave_of["10"]
    assert wave_of["0"] == 0                                 # 入口在首波

    # 矛盾 DAG:把 5A 声明成依赖 6(循环)→ 启动即报,不跑到一半
    dag = load_dag()
    import copy
    broken = copy.deepcopy(dag)
    broken["stage_graph"]["6"]["next"] = ["5A"]  # 6 完成 → 5A,与 5A→6 形成环
    try:
        build_execution_plan(broken)
        assert False, "循环 DAG 应启动即报"
    except ValueError as e:
        assert "循环" in str(e), e

    # parallel_groups 声明与分层矛盾(把 1/2 声明成并行组但它们是串行链)
    inconsistent = copy.deepcopy(dag)
    inconsistent["parallel_groups"]["fake"] = {"branches": ["1", "2"], "join_at": "3"}
    try:
        build_execution_plan(inconsistent)
        assert False, "矛盾的并行组声明应报错"
    except ValueError as e:
        assert "parallel_groups" in str(e), e


def main():
    test_auto_mode_completes_loop()
    test_java_vue_receipts_match_actual_codegen_agents()
    test_non_auto_directives_include_budgeted_knowledge_context()
    test_non_auto_blocks_at_unmet_prereq()
    test_rerun_is_idempotent_resume()
    test_parallel_wave_codegen_thread_safe()
    test_live_auto_mock_partial_script_degrades_to_skip()
    test_execution_plan_from_dag()
    print("OK: runner 自测通过(8 组断言)")


if __name__ == "__main__":
    main()
