#!/usr/bin/env python3
"""编排 runner —— 确定性主循环:按 DAG 驱动 12 阶段(设计文档 §15「主 Agent 只调度」)。

第一阶段:任何阶段到达终态必须经 lib/transition(FSM + 前置 + 产出 + receipt +
checkpoint + evidence 全门控)。runner 不再直接写 state.json。

- 确定性阶段(0 / 5A / 5B / 6 / 10)真实执行,经 transition 完成
- LLM 阶段(3 / 4 / 7 / 8 / 9)签发委派指令(dispatch directive),不完成
- --auto 演示模式:LLM 阶段显式带批准跳过(record skip),checkpoint 自动 approve
- 非 auto 模式:checkpoint 阶段停在 checkpoint_pending;前置未就绪的推进会被
  transition 真实阻断(不可绕过的体现)
- --live 模式:LLM 阶段经 tool calling 主循环真实执行(lib/llm_dispatch),
  运行时可选 openai(OpenAI 兼容网关)或 mock(脚本驱动,演示/测试)

用法:
    python3 lib/runner.py run <contract> --out <dir> [--state <state.json>] [--stacks react,vue,node,java] [--auto]
    python3 lib/runner.py run <contract> --out gen --live --llm-runtime mock --llm-script script.json --auto
    python3 lib/runner.py status [--state <state.json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# 使 `python3 lib/runner.py` 直接执行时也能 import lib.* 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.context_orchestrator import build_dispatch_context  # noqa: E402
from lib.contract.consistency import cross_stack_check  # noqa: E402
from lib.contract.generator import write_out  # noqa: E402
from lib.contract.parser import parse_contract  # noqa: E402
from lib.contract.verify import verify  # noqa: E402
from lib.delegation import issue_receipt, load_policy, resolve_subagents  # noqa: E402
from lib.state_manager import actionable_stages, init_state, read_state, summary  # noqa: E402
from lib.transition import TransitionError, complete_stage, skip_stage, start_stage  # noqa: E402

# 确定性阶段(可直接执行)vs LLM 阶段(签发委派指令)
DETERMINISTIC = {"0", "5A", "5B", "6", "10"}

# 演示模式(契约已提供)下跳过的 LLM 阶段及其理由。
# planner 只决策 1/2/3/4(基于已有产物),7/8/9 属演示场景缺省,保留在此表作 fallback 合并。
SKIP_STAGES = {
    "1": ("orchestrator/requirements-analyst", "契约已提供(输入即契约),需求以契约为准"),
    "2": ("contract/contract-designer", "契约已提供(输入即契约),契约设计以契约为准"),
    "3": ("orchestrator/services-analyst", "演示模式:单仓库,不产技术方案"),
    "4": ("orchestrator/git-client", "演示模式:单仓库本地开发,不新建分支"),
    "7": ("quality/code-review", "演示模式:无真实 PR 评审"),
    "8": ("quality/test-case-generator", "演示模式:无真实测试用例"),
    "9": ("orchestrator/deployer", "演示模式:无真实提测部署"),
}


def _planned_skips() -> dict:
    """P0-8: 路径决策来自 planner(数据)而非硬编码控制流;SKIP_STAGES 作 fallback 合并。

    planner 说不 skip 的阶段沿用 SKIP_STAGES 的演示理由;planner 说 skip 的
    理由更准确反映"为什么可以跳过"(输入即契约)。skip 本身仍走 skip_stage
    全门控(receipt/approved_by),FSM 兜底汇合点(6/9)不可跳。
    """
    from lib.planner.planner import plan
    inputs = {"has_contract": True, "has_tech_plan": False, "has_branch": False}
    decisions = plan(inputs)["stages"]
    merged: dict = {}
    for sid, (sub, fallback_reason) in SKIP_STAGES.items():
        if decisions.get(sid) == "skip":
            merged[sid] = (sub, f"planner 确认: {fallback_reason}")
        else:
            merged[sid] = (sub, fallback_reason)
    return merged


def _change_id(contract: Path) -> str:
    return contract.stem


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# 事件/trajectory 落盘(事件溯源):单条 JSON append,Ctrl-C/崩溃不丢已发生事件。
EVENTS_FILE = "events.jsonl"
TRANSCRIPTS_DIR = "transcripts"
# 落盘时对超长字符串截断(如 write_file 的 content),避免日志膨胀
_MAX_DETAIL_CHARS = 2000


def _truncate_deep(value, limit: int = _MAX_DETAIL_CHARS):
    """深度截断 dict/list 内的超长字符串(落盘旁路记录专用,不影响内存事件)。"""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"...[truncated {len(value) - limit} chars]"
    if isinstance(value, dict):
        return {k: _truncate_deep(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate_deep(v, limit) for v in value]
    return value


def _persist_event(out_dir: Path, change_id: str, event: dict) -> None:
    """单条事件 append 到 events.jsonl(每条即时落盘,append-only 天然崩溃安全)。"""
    events_file = Path(out_dir) / EVENTS_FILE
    events_file.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"at": _now(), "change_id": change_id, **_truncate_deep(event)},
        ensure_ascii=False, default=str,
    )
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _persist_transcript(out_dir: Path, stage: str, result: dict) -> None:
    """--live 阶段的 trajectory 落盘:完整 tool calling 过程,供复盘与 evals 回放(P2-3)。"""
    transcript = result.get("transcript")
    if not transcript:
        return
    tdir = Path(out_dir) / TRANSCRIPTS_DIR
    tdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": stage,
        "ok": result.get("ok"),
        "status": result.get("status"),
        "tool_call_count": result.get("tool_call_count"),
        "reasons": result.get("reasons"),
        "at": _now(),
        "transcript": _truncate_deep(transcript),
    }
    (tdir / f"stage-{stage}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def _collect_coverage(group: List[str], repo: Optional[str | Path]) -> str:
    """P0-6: 尽力采集真实覆盖率;无命令/无仓库/失败 → 降级为 G1 骨架说明字符串。

    只采集上报,不做门控拦截(strong-gate 留给 P2-4 接 checkpoint)。命令来自
    各栈 adapter 的 COVERAGE 常量(项目自带,非 LLM 可控)。
    """
    from lib.coverage_collector import collect
    fallback = "G1 verified(骨架生成,未跑真实覆盖率)"
    if not repo:
        return fallback
    parts = []
    for s in group:
        r = collect(s, str(repo))
        if "error" in r:
            return fallback  # 任一栈采集失败即降级,保持 outputs 单一字符串形态
        line_pct = (r.get("report") or {}).get("changed_line")
        parts.append(f"{s}: {line_pct}%" if line_pct is not None else f"{s}: no-line-coverage")
    return "; ".join(parts) if parts else fallback


def _stage_in_terminal(state_file: Path, sid: str) -> bool:
    """阶段已达终态(completed/skipped)→ 重跑时跳过实体工作(幂等 resume)。

    必须在实体工作(如 write_out 文件重写)之前检查,否则已完成阶段的产物
    会先被覆盖、再被 transition 门控拦住,留下与 state 不一致的文件。
    """
    from lib.state_manager import TERMINAL
    return read_state(state_file)["stages"].get(sid, {}).get("state") in TERMINAL


class _EventLog(list):
    """内存事件列表 + 每条即时落盘 events.jsonl(事件溯源)。"""

    def __init__(self, out_dir: Optional[str | Path] = None, change_id: str = ""):
        super().__init__()
        self._out_dir = Path(out_dir) if out_dir else None
        self._change_id = change_id

    def emit(self, event: dict) -> None:
        self.append(event)
        if self._out_dir:
            _persist_event(self._out_dir, self._change_id, event)


def _stage_subagents(stage: str, policy: dict, stacks: Optional[List[str]] = None, *, for_skip: bool = False) -> List[str]:
    """解析阶段本次实际执行（或跳过确认）的 Agent。"""
    subagents = resolve_subagents(stage, stacks, policy, for_skip=for_skip)
    if not subagents:
        raise ValueError(f"阶段 {stage} 未解析到可用 subagent")
    return subagents


def build_execution_plan(dag: Optional[dict] = None) -> List[List[str]]:
    """从 workflow-dag.json 生成拓扑波次执行计划(工作流定义与执行解耦)。

    规则:
    - Kahn 拓扑分层:依赖全部满足的阶段进同一波,天然覆盖 parallel_groups
      (5A/5B、7/8 前置相同 → 自动同波;汇合点 6/9 前置含全部分支 → 自动后置);
    - parallel_groups 数据仍读出来做一层校验:声明的 branches 必须落进同一波,
      不满足即 DAG 自身矛盾,启动即报(而不是跑一半才卡住);
    - 计划只是顺序建议,真正的可行性仍由 transition 门控裁决(不可绕过不变)。

    返回波次列表,如 [["0"], ["1"], ["2"], ..., ["5A","5B"], ["6"], ["7","8"], ["9"], ["10"]]。
    """
    if dag is None:
        from lib.state_manager import load_dag
        dag = load_dag()
    graph = dag.get("stage_graph", {})

    # stage_graph[sid].next = 我完成后谁可推进 → 反转为依赖边
    deps: dict = {sid: set() for sid in graph}
    for sid, spec in graph.items():
        for nxt in (spec or {}).get("next", []):
            if nxt in deps:
                deps[nxt].add(sid)

    waves: List[List[str]] = []
    remaining = set(graph)
    while remaining:
        wave = sorted(sid for sid in remaining if not (deps[sid] - (set(graph) - remaining)))
        if not wave:
            raise ValueError(f"workflow-dag 存在循环依赖,卡在: {sorted(remaining)}")
        waves.append(wave)
        remaining -= set(wave)

    # 校验 parallel_groups 声明:branches 必须同波(数据自洽性检查)
    for gname, g in dag.get("parallel_groups", {}).items():
        member_waves = {i for i, w in enumerate(waves) for m in g.get("branches", []) if m in w}
        if len(member_waves) > 1:
            raise ValueError(f"parallel_groups[{gname}] 声明的分支未落进同一波,DAG 自相矛盾")
    return waves


def _directive(
    stage: str,
    policy: dict,
    contract: str,
    entities: Optional[List[str]] = None,
    repo: Optional[str | Path] = None,
    context_max_tokens: int = 4000,
) -> dict:
    """为 LLM 阶段生成包含受预算知识上下文的委派指令。"""
    subagents = _stage_subagents(stage, policy)
    receipt = issue_receipt(stage, subagents, token="runner")
    context = build_dispatch_context(stage, contract, entities, repo, context_max_tokens)
    return {
        "stage": stage,
        "subagent": subagents[0] if len(subagents) == 1 else None,
        "subagents": subagents,
        "receipt": receipt,
        "contract": contract,
        "context": context,
        "note": f"需要 {', '.join(subagents)} 执行(LLM 阶段,runner 仅签发委派)",
    }


def _register(state_file: Path, receipt: dict) -> dict:
    """签发后登记 receipt 到 state(防伪造;complete/skip 前必须登记)。"""
    from lib.delegation import register_receipt
    register_receipt(state_file, receipt)
    return receipt


def _try_transition(state_file: Path, fn, events: "_EventLog", stage: str, kind: str, detail: str) -> Optional[dict]:
    """执行一个经 transition 的动作;失败记录 blocked 事件。"""
    try:
        res = fn()
        status = res.get("status") or res.get("state")
        events.emit({"stage": stage, "kind": kind, "detail": detail, "status": status})
        return res
    except TransitionError as e:
        events.emit({"stage": stage, "kind": "blocked", "detail": f"{detail} -> {e}"})
        return None


def _start_then_complete(state_file: Path, stage: str, **kwargs) -> dict:
    """start(前置校验)→ complete(产出/receipt/checkpoint 门控)的顺序执行。"""
    start_stage(state_file, stage)
    return complete_stage(state_file, stage, **kwargs)


def _build_stage_client(llm_runtime: str, llm_script: Optional[str | Path], stage: str):
    """为某个 LLM 阶段构造运行时客户端。mock 脚本支持 {"stages": {<stage>: [...]}} 分阶段。"""
    if llm_runtime == "openai":
        from lib.llm_client import OpenAICompatClient
        return OpenAICompatClient()
    if llm_runtime == "mock":
        from lib.llm_client import MockLLMClient
        if not llm_script:
            raise ValueError("--live --llm-runtime mock 需要 --llm-script(JSON 脚本)")
        data = json.loads(Path(llm_script).read_text(encoding="utf-8"))
        steps = data.get("stages", {}).get(stage) if isinstance(data, dict) else data
        if steps is None:
            raise ValueError(f"mock 脚本缺少阶段 {stage} 的步骤(stages.{stage})")
        return MockLLMClient(steps)
    raise ValueError(f"未知 llm-runtime: {llm_runtime}(可选 mock / openai)")


def _run_llm_stage(
    state_file: Path,
    sid: str,
    policy: dict,
    contract: Path,
    entities: List[str],
    repo: Optional[str | Path],
    context_max_tokens: int,
    *,
    live: bool,
    llm_runtime: str,
    llm_script: Optional[str | Path],
    llm_max_turns: int,
    auto: bool,
    events: "_EventLog",
) -> None:
    """LLM 阶段统一入口:默认仅签发 directive;--live 时经 tool calling 循环真实执行。"""
    directive = _directive(sid, policy, str(contract), entities, repo, context_max_tokens)
    if not live:
        events.emit({"stage": sid, "kind": "agent", "detail": directive})
        return
    from lib.llm_dispatch import run_llm_stage
    res = run_llm_stage(
        directive, state_file,
        client=_build_stage_client(llm_runtime, llm_script, sid),
        contract_path=contract,
        workdir=repo or Path.cwd(),
        max_turns=llm_max_turns,
        auto_approve=auto,
    )
    events.emit({"stage": sid, "kind": "llm", "detail": res})
    # trajectory 落盘(--live 独有:完整 tool calling 过程)
    _persist_transcript(events._out_dir, sid, res)  # noqa: SLF001 — 内部协作类


def run(
    contract: str | Path,
    out_dir: str | Path,
    state_file: str | Path,
    stacks: List[str],
    auto: bool = False,
    repo: Optional[str | Path] = None,
    context_max_tokens: int = 4000,
    live: bool = False,
    llm_runtime: str = "mock",
    llm_script: Optional[str | Path] = None,
    llm_max_turns: int = 12,
) -> dict:
    contract = Path(contract)
    state_file = Path(state_file)
    policy = load_policy()
    contract_model = parse_contract(contract)
    entities = sorted(contract_model.get("schemas", {}).keys())

    # P1-7: 启动环境自检(ACI:报错即给出可行动的安装命令;critical 缺失 fail-fast)
    from lib.self_heal import heal
    env = heal()
    if not env["ok"]:
        raise RuntimeError(
            "环境自检失败(critical 依赖缺失): "
            + "; ".join(f"{d['name']} → {d['install']}" for d in env["missing"] if d["critical"])
        )

    # Stage 0: 初始化
    if not state_file.exists():
        init_state(state_file, _change_id(contract))

    # KPI 观测:契约规模(需求吞吐的分母)——复用已 parse 的模型,零额外计算;
    # 已存在则不覆盖(重跑 resume 时保持首次口径)
    state = read_state(state_file)
    if not state.get("contract_stats"):
        schemas = contract_model.get("schemas", {})
        state["contract_stats"] = {
            "endpoints": len(contract_model.get("endpoints", [])),
            "schemas": len(schemas),
            "fields": sum(
                len(s.get("properties") or []) if isinstance(s, dict) else 0
                for s in schemas.values()
            ),
        }
        from lib.state_manager import write_state
        write_state(state_file, state)

    events = _EventLog(out_dir=out_dir, change_id=_change_id(contract))
    planned_skips = _planned_skips() if auto else SKIP_STAGES

    def record(stage: str, kind: str, detail) -> None:
        events.emit({"stage": stage, "kind": kind, "detail": detail})

    # ---- 确定性阶段 handler(每阶段的实体工作) ----
    backend = [s for s in stacks if s in ("node", "java")]
    frontend = [s for s in stacks if s in ("react", "vue")]

    def _stage_init() -> None:
        _try_transition(
            state_file,
            lambda: _start_then_complete(
                state_file, "0",
                outputs={"execution_plan": f"contract-driven SDLC: {contract.name}"},
                receipt=_register(state_file, issue_receipt("0", "orchestrator/init", "runner")),
                evidence=[{"type": "contract", "detail": str(contract), "at": _now()}],
            ),
            events, "0", "done", "初始化 state(经 transition 门控)",
        )

    def _codegen_task(sid: str, group: List[str]) -> None:
        """单个 codegen 阶段的完整工作(生成+G1 门+transition),线程安全:
        state.json 并发写由 transition 模块级锁串行化(P1-6),生成产物各栈目录天然隔离。"""
        if _stage_in_terminal(state_file, sid):
            # 幂等 resume:已完成/已跳过 → 不重写生成文件,避免"文件先被覆盖、
            # 再被 transition 拦住"导致的产物与 state 不一致
            events.emit({"stage": sid, "kind": "resume_skip", "detail": "已达终态,跳过实体工作"})
            return
        if not group:
            subagents = _stage_subagents(sid, policy, for_skip=True)
            _try_transition(
                state_file,
                lambda sid=sid, subagents=subagents: skip_stage(
                    state_file, sid,
                    reason="无该端技术栈",
                    approved_by="runner:auto",
                    receipt=_register(state_file, issue_receipt(sid, subagents, "runner", action="skip")),
                ),
                events, sid, "skip", "无该端技术栈",
            )
            return
        try:
            files = []
            for s in group:
                written = write_out(contract, s, Path(out_dir) / s)
                verify(contract, s)  # G1 生成门
                files.extend(f"{s}/{f}" for f in written)
            _try_transition(
                state_file,
                lambda sid=sid, files=files, group=group: _start_then_complete(
                    state_file, sid,
                    outputs={
                        "changed_files": files,
                        "coverage": _collect_coverage(group, repo),
                    },
                    receipt=_register(state_file, issue_receipt(sid, _stage_subagents(sid, policy, group), "runner")),
                    checkpoint_decision="approve" if auto else None,
                    auto_approve=auto,
                    evidence=[{"type": "codegen", "detail": f"{sid}: {', '.join(group)}", "at": _now()}],
                ),
                events, sid, "done", f"codegen + G1 门:{', '.join(group)}",
            )
        except Exception as e:  # codegen 本身失败
            events.emit({"stage": sid, "kind": "failed", "detail": f"codegen 异常: {e}"})

    def _stage_consistency() -> None:
        try:
            r = cross_stack_check(contract)
            _try_transition(
                state_file,
                lambda: _start_then_complete(
                    state_file, "6",
                    outputs={"consistency_report": json.dumps(r, ensure_ascii=False)},
                    receipt=_register(state_file, issue_receipt("6", "contract/consistency-checker", "runner")),
                    checkpoint_decision="approve" if auto else None,
                    auto_approve=auto,
                    evidence=[{"type": "consistency", "detail": f"ok={r['ok']}", "at": _now()}],
                ),
                events, "6", "done", f"跨栈一致性: {r['ok']}",
            )
        except Exception as e:
            record("6", "failed", f"一致性检查异常: {e}")

    def _stage_delivery() -> None:
        _try_transition(
            state_file,
            lambda: _start_then_complete(
                state_file, "10",
                outputs={"delivery_report": f"交付报告(见 summary): {contract.name}"},
                receipt=_register(state_file, issue_receipt("10", "orchestrator/notifier", "runner")),
                checkpoint_decision="approve" if auto else None,
                auto_approve=auto,
                evidence=[{"type": "delivery", "detail": "runner 汇总", "at": _now()}],
            ),
            events, "10", "done", "交付报告(见 summary)",
        )

    def _stage_handler(sid: str) -> None:
        """按阶段分发实体工作:确定性阶段走专属 handler,LLM 阶段统一走委派入口。"""
        if sid == "0":
            _stage_init()
        elif sid == "5A":
            _codegen_task(sid, backend)
        elif sid == "5B":
            _codegen_task(sid, frontend)
        elif sid == "6":
            _stage_consistency()
        elif sid == "10":
            _stage_delivery()
        else:  # LLM 阶段(1/2/3/4/7/8/9)
            if auto and not live:
                sub, reason = planned_skips[sid]
                _try_transition(
                    state_file,
                    lambda sid=sid, sub=sub, reason=reason: skip_stage(
                        state_file, sid,
                        reason=reason,
                        approved_by="runner:auto",
                        receipt=_register(state_file, issue_receipt(sid, sub, "runner")),
                    ),
                    events, sid, "skip", reason,
                )
            else:
                _run_llm_stage(
                    state_file, sid, policy, contract, entities, repo, context_max_tokens,
                    live=live, llm_runtime=llm_runtime, llm_script=llm_script,
                    llm_max_turns=llm_max_turns, auto=auto, events=events,
                )

    # ---- 数据驱动主循环:按 DAG 拓扑波次执行(工作流定义与执行解耦) ----
    # 波次计划来自 workflow-dag.json(Kahn 分层):5A/5B 与 7/8 各自同波并行,
    # 汇合点 6/9 自动后置;真正的可行性仍由 transition 门控逐阶段裁决。
    plan = build_execution_plan()
    from lib.parallel_wave_scheduler import run as run_waves
    for wave in plan:
        if len(wave) == 1:
            _stage_handler(wave[0])
        else:
            # 波内并行:完成事件顺序不确定,events 断言按集合比较
            run_waves({sid: [] for sid in wave}, executor=lambda sid: _stage_handler(sid))

    return {
        "ok": True,
        "contract": str(contract),
        "state": str(state_file),
        "summary": summary(state_file),
        "events": events,
        "next_actionable": actionable_stages(state_file),
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="fe-be-contract-harness 编排 runner")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="按 DAG 驱动工作流(经唯一 transition 门控)")
    r.add_argument("contract")
    r.add_argument("--out", default="gen")
    r.add_argument("--state", default="state.json")
    r.add_argument("--stacks", default="react,vue,node,java")
    r.add_argument("--auto", action="store_true", help="演示自动模式(LLM 阶段显式跳过 + checkpoint 自动批准)")
    r.add_argument("--repo", default=None, help="目标仓库路径；用于向 LLM 阶段注入相关仓库知识")
    r.add_argument("--context-max-tokens", type=int, default=4000, help="单次委派的知识上下文 token 预算")
    r.add_argument("--live", action="store_true", help="LLM 阶段真实执行(tool calling 主循环,而非仅签发 directive)")
    r.add_argument("--llm-runtime", default="mock", choices=["mock", "openai"], help="LLM 运行时:mock=脚本驱动,openai=OpenAI 兼容网关")
    r.add_argument("--llm-script", default=None, help="mock 运行时脚本(JSON,支持 stages.<stage> 分阶段步骤数组)")
    r.add_argument("--llm-max-turns", type=int, default=12, help="单阶段 tool calling 最大轮次")

    s = sub.add_parser("status", help="查看状态")
    s.add_argument("--state", default="state.json")

    rep = sub.add_parser("report", help="run 观测报告(阶段耗时/门控拦截/LLM 行为/人工返工)")
    rep.add_argument("--out", default="gen", help="生成目录(events.jsonl 所在)")
    rep.add_argument("--state", default="state.json")

    args = p.parse_args(argv)

    if args.cmd == "run":
        stacks = [x.strip() for x in args.stacks.split(",") if x.strip()]
        result = run(
            args.contract, args.out, args.state, stacks, auto=args.auto, repo=args.repo,
            context_max_tokens=args.context_max_tokens, live=args.live,
            llm_runtime=args.llm_runtime, llm_script=args.llm_script,
            llm_max_turns=args.llm_max_turns,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    elif args.cmd == "status":
        print(json.dumps(summary(Path(args.state)), ensure_ascii=False, indent=2))
        return 0
    elif args.cmd == "report":
        from lib.run_report import append_metrics, build_report
        report = build_report(args.out, Path(args.state))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        append_metrics(args.out, report)  # KPI 趋势埋点(跨 run 基线)
        return 0
    else:
        p.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
