#!/usr/bin/env python3
"""唯一状态迁移入口 —— 阶段到达终态(completed/skipped)必须经过本模块(第一阶段)。

把以下门控串成一条不可绕过的执行链:
1. FSM 转换合法性(workflow_fsm.validate_transition)
2. DAG 前置阶段全部终态(all_prereqs_completed)
3. 必需产出完整(required_outputs,含 Stage 1 的 SDD 结构化 Spec 校验)
4. 委派 fail-closed(dispatch receipt 有效且 subagent 匹配)
5. checkpoint(人工卡点):approve/skip 才可终态;revise 回到 running
6. 审计落盘:outputs / receipt / checkpoint / evidence / completed_at

约定:
- state_manager.set_stage_state 保留为低层运维写(恢复/调试),正式完成一律走本模块。
- 确定性阶段(0/5A/5B/6/10)由 runner 签发 receipt(token=runner);LLM 阶段由子 Agent 回传 receipt。

用法(CLI):
    python3 lib/transition.py dispatch <state> <stage> --subagent <agent>          # 一键委派:签发+登记+start(receipt 自动落盘 receipts/)
    python3 lib/transition.py hint <state>                                        # 下一步导航:当前可推进阶段 + 建议命令
    python3 lib/transition.py register <state> --receipt <json>           # 登记委派 receipt(防伪造)
    python3 lib/transition.py start <state> <stage>
    python3 lib/transition.py complete <state> <stage> --outputs <json> --receipt <json> [--checkpoint approve|skip] [--evidence <json>] [--auto]
        # 大 JSON 建议用 --outputs-file/--receipt-file/--evidence-file 传文件路径,避免 shell 转义问题
    python3 lib/transition.py skip <state> <stage> --reason <text> --approved-by <who> [--receipt <json>] [--evidence <json>]
    python3 lib/transition.py fail <state> <stage> [--reason <text>]
    python3 lib/transition.py retry <state> <stage>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# 使 `python3 lib/transition.py` 直接执行时也能 import lib.* 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.checkpoint_manager import decide, requires_checkpoint
from lib.delegation import (
    allowed_subagents,
    consume_receipt,
    load_policy,
    validate_dispatch,
    validate_subagent_match,
)
from lib.state_manager import read_state, write_state
from lib.workflow_fsm import WorkflowFSM


class TransitionError(Exception):
    """门控未通过。reasons 为结构化原因列表。"""

    def __init__(self, message: str, reasons: Optional[List[str]] = None):
        super().__init__(message)
        self.reasons = reasons or [message]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stage_states(state: dict) -> Dict[str, str]:
    return {sid: s["state"] for sid, s in state["stages"].items()}


def _check_stage(state: dict, stage_id: str) -> None:
    if stage_id not in state["stages"]:
        raise TransitionError(f"unknown stage: {stage_id}")


def _stage_discovery(stage_id: str) -> dict:
    """阶段可发现性信息:允许的执行 Agent / 必需产出 / checkpoint 类型。
    在 start 与 dispatch 时前置告知,避免执行者事后被 fail-closed 拦下。"""
    fsm = WorkflowFSM()
    return {
        "allowed_subagents": allowed_subagents(stage_id),
        "required_outputs": fsm.required_outputs(stage_id),
        "checkpoint": fsm.checkpoint_type(stage_id),
    }


def _validate_stage_output_semantics(stage_id: str, outputs: dict) -> List[str]:
    """阶段专属产出语义校验(机验,拒绝自由文本自述)。

    Stage 9(deploy):deploy_result 必须是结构化对象,健康检查/冒烟测试结果逐条机验:
        {"environment": "http://...", "ok": true,
         "health_check": {"url": "/actuator/health", "status_code": 200},
         "smoke_tests": [{"name": "login", "status_code": 200, "passed": true}]}
    """
    problems: List[str] = []
    if stage_id != "9":
        return problems
    dr = outputs.get("deploy_result")
    if dr is None:
        return problems  # 缺失由 FSM required_outputs 把关
    if not isinstance(dr, dict):
        problems.append(
            "deploy_result 必须是结构化对象(含 environment/ok/health_check/smoke_tests),"
            "不接受自由文本自述"
        )
        return problems
    if dr.get("ok") is False:
        problems.append("deploy_result.ok=false(部署自述失败,不能作为完成证据)")
    hc = dr.get("health_check")
    if isinstance(hc, dict):
        code = hc.get("status_code")
        if code is not None and not (200 <= code < 300):
            problems.append(f"deploy_result.health_check.status_code={code}(非 2xx)")
    for i, t in enumerate(dr.get("smoke_tests") or []):
        if not isinstance(t, dict):
            continue
        code = t.get("status_code")
        if code is not None and not (200 <= code < 300):
            problems.append(
                f"deploy_result.smoke_tests[{i}]({t.get('name', '?')}) status_code={code}(非 2xx)"
            )
        if t.get("passed") is False:
            problems.append(f"deploy_result.smoke_tests[{i}]({t.get('name', '?')}) passed=false")
    return problems


def hint(state_file: Path | str) -> dict:
    """下一步导航:读 state,返回可推进阶段 + 建议命令(只读,不迁移状态)。"""
    sf = Path(state_file)
    state = read_state(sf)
    fsm = WorkflowFSM()
    st = _stage_states(state)

    in_flight, actionable, failed = [], [], []
    for sid in fsm.stages():
        s = st[sid]
        if s == "failed":
            failed.append(sid)
        elif s in ("running", "checkpoint_pending"):
            in_flight.append(sid)
        elif s not in ("completed", "skipped"):
            ok, _ = fsm.all_prereqs_completed(sid, st)
            if ok:
                actionable.append(sid)

    suggestions: List[dict] = []
    for sid in failed:
        suggestions.append({
            "stage": sid, "state": "failed",
            "action": "retry",
            "command": f"python3 lib/transition.py retry {sf} {sid}",
        })
    for sid in in_flight:
        s = st[sid]
        disc = _stage_discovery(sid)
        if s == "checkpoint_pending":
            suggestions.append({
                "stage": sid, "state": s,
                "action": "人工确认 checkpoint(approve/skip/revise),已落盘产出会自动复用",
                "command": f"python3 lib/transition.py complete {sf} {sid} --checkpoint approve",
            })
        else:
            suggestions.append({
                "stage": sid, "state": s,
                "action": "完成阶段(产出满足 required_outputs 时)",
                "required_outputs": disc["required_outputs"],
                "command": f"python3 lib/transition.py complete {sf} {sid} --outputs-file <f> --receipt-file <f>",
            })
    for sid in actionable:
        disc = _stage_discovery(sid)
        first_agent = disc["allowed_subagents"][0] if disc["allowed_subagents"] else "<agent>"
        suggestions.append({
            "stage": sid, "state": "pending",
            "action": "委派执行(dispatch 一键:签发+登记+start)",
            "allowed_subagents": disc["allowed_subagents"],
            "required_outputs": disc["required_outputs"],
            "checkpoint": disc["checkpoint"],
            "command": f"python3 lib/transition.py dispatch {sf} {sid} --subagent {first_agent}",
        })

    done = sum(1 for s in st.values() if s in ("completed", "skipped"))
    return {
        "ok": True,
        "change_id": state.get("change_id"),
        "progress": f"{done}/{len(st)}",
        "suggestions": suggestions,
        "finished": not suggestions,
        "message": "全部阶段已终态,流程结束" if not suggestions else None,
    }


def _validate_evidence(evidence: List[dict], state_file: Path) -> List[str]:
    """evidence 结构化校验(fail-closed 延伸到证据层):
    - 每条必须有非空 type;
    - artifact_path 若存在必须真实存在(相对路径以仓库根 = state 文件上两级为基准);
    - exit_code 非零不能作为完成证据。
    """
    problems: List[str] = []
    repo_root = Path(state_file).parent.parent  # 约定: state 位于 <repo>/.harness/state.json
    for i, ev in enumerate(evidence):
        if not isinstance(ev, dict) or not str(ev.get("type") or "").strip():
            problems.append(
                f"evidence[{i}] 缺少 type 字段"
                "(结构化证据要求 {{type, detail 或 command, artifact_path?, exit_code?}})"
            )
            continue
        artifact = ev.get("artifact_path")
        if artifact:
            p = Path(artifact)
            if not p.is_absolute():
                candidates = [repo_root / artifact, Path.cwd() / artifact]
                p = next((c for c in candidates if c.exists()), candidates[0])
            if not p.exists():
                problems.append(f"evidence[{i}].artifact_path 不存在: {artifact}(以仓库根 {repo_root} 为基准)")
        exit_code = ev.get("exit_code")
        if exit_code is not None and exit_code != 0:
            problems.append(f"evidence[{i}].exit_code={exit_code}(非零退出码不能作为完成证据)")
    return problems


def _check_prereqs(state_file: Path, stage_id: str) -> None:
    fsm = WorkflowFSM()
    state = read_state(state_file)
    ok, waiting = fsm.all_prereqs_completed(stage_id, _stage_states(state))
    if not ok:
        raise TransitionError(f"阶段 {stage_id} 前置未就绪: {waiting}", [f"prereq_not_ready: {waiting}"])


def start_stage(state_file: Path | str, stage_id: str) -> dict:
    """pending → running。校验前置全部终态。"""
    sf = Path(state_file)
    state = read_state(sf)
    _check_stage(state, stage_id)
    fsm = WorkflowFSM()
    current = state["stages"][stage_id]["state"]
    ok, nxt = fsm.validate_transition(current, "start")
    if not ok:
        raise TransitionError(f"阶段 {stage_id} 当前状态 {current} 不能 start")
    ok_prereq, waiting = fsm.all_prereqs_completed(stage_id, _stage_states(state))
    if not ok_prereq:
        raise TransitionError(f"阶段 {stage_id} 前置未就绪: {waiting}", [f"prereq_not_ready: {waiting}"])
    state["stages"][stage_id]["state"] = nxt.value
    state["stages"][stage_id]["updated_at"] = _now()
    state["current_stage"] = stage_id
    write_state(sf, state)
    return {"ok": True, "stage": stage_id, "state": nxt.value, **_stage_discovery(stage_id)}


def complete_stage(
    state_file: Path | str,
    stage_id: str,
    *,
    outputs: Optional[dict] = None,
    receipt: Optional[dict] = None,
    checkpoint_decision: Optional[str] = None,
    evidence: Optional[List[dict]] = None,
    auto_approve: bool = False,
) -> dict:
    """把 running / checkpoint_pending 的阶段推到终态,经过全部门控。

    返回:
    - {"ok": True, "status": "completed"|"skipped", ...} 终态
    - {"ok": True, "status": "checkpoint_pending", ...}  需要人工确认(非 auto 且未提供 decision)
    - {"ok": False, "status": "revise", ...}             人工要求修订,阶段回到 running
    - 抛 TransitionError:门控未通过(产出缺失/receipt 无效/前置未就绪/checkpoint 非法)
    """
    sf = Path(state_file)
    state = read_state(sf)
    _check_stage(state, stage_id)
    fsm = WorkflowFSM()
    current = state["stages"][stage_id]["state"]
    if current not in ("running", "checkpoint_pending"):
        raise TransitionError(f"阶段 {stage_id} 当前状态 {current} 不能 complete")

    # checkpoint_pending 复跑:合并已落盘的产出/receipt/evidence(修复:pending 时保存的数据被丢弃)
    saved = state["stages"][stage_id]
    if current == "checkpoint_pending":
        if receipt is None:
            receipt = saved.get("receipt")
        merged = dict(saved.get("outputs") or {})
        merged.update(outputs or {})
        outputs = merged
        if evidence:
            evidence = list(saved.get("evidence") or []) + list(evidence)
        else:
            evidence = list(saved.get("evidence") or [])
    else:
        outputs = outputs or {}
        evidence = list(evidence or [])
    problems: List[str] = []

    # 1. 前置就绪(幂等校验,start 时已查)
    ok_prereq, waiting = fsm.all_prereqs_completed(stage_id, _stage_states(state))
    if not ok_prereq:
        problems.append(f"前置未就绪: {waiting}")

    # 2. 必需产出
    ok_out, missing = fsm.validate_completion(stage_id, outputs)
    if not ok_out:
        problems.append(f"缺少必需产出: {missing}")

    # 3. 委派 fail-closed(required_stages 中的阶段必须有合法且已登记的 receipt)
    policy = load_policy()
    if stage_id in policy.get("required_stages", []):
        if not receipt:
            problems.append(f"阶段 {stage_id} 缺少 dispatch receipt(委派 fail-closed)")
        else:
            dres = validate_dispatch(stage_id, receipt, outputs, policy, state_file=sf)
            if not dres["ok"]:
                problems.extend(dres["reasons"])

    # 3.5 evidence 结构化校验(证据层 fail-closed)
    problems.extend(_validate_evidence(evidence, sf))

    # 3.6 阶段专属产出语义校验(如 Stage 9 deploy_result 机验)
    problems.extend(_validate_stage_output_semantics(stage_id, outputs))

    if problems:
        problems = list(dict.fromkeys(problems))  # 去重(FSM 与 validate_dispatch 会重复报缺失产出)
        raise TransitionError(f"阶段 {stage_id} 门控未通过: {'; '.join(problems)}", problems)

    # 4. checkpoint 门控
    ct = fsm.checkpoint_type(stage_id)
    checkpoint_record = None
    if requires_checkpoint(stage_id):
        if checkpoint_decision is None and not auto_approve:
            # 进入人工卡点,先把已提供数据落盘
            state["stages"][stage_id]["state"] = "checkpoint_pending"
            state["stages"][stage_id]["outputs"] = outputs
            state["stages"][stage_id]["receipt"] = receipt
            state["stages"][stage_id]["evidence"] = evidence
            state["stages"][stage_id]["updated_at"] = _now()
            state["current_stage"] = stage_id
            write_state(sf, state)
            return {
                "ok": True, "stage": stage_id, "status": "checkpoint_pending",
                "checkpoint": ct,
                "message": f"阶段 {stage_id} 需人工确认(checkpoint={ct})",
            }
        decision_input = checkpoint_decision if checkpoint_decision is not None else "approve"
        dec = decide(stage_id, decision_input)
        if not dec["ok"]:
            raise TransitionError(f"阶段 {stage_id} checkpoint 未通过: {dec['reason']}", [f"checkpoint_{ct}_forbid_{dec['decision']}"])
        if dec["decision"] == "revise":
            state["stages"][stage_id]["state"] = "running"
            state["stages"][stage_id]["updated_at"] = _now()
            write_state(sf, state)
            return {
                "ok": False, "stage": stage_id, "status": "revise",
                "message": "人工要求修订,阶段回到 running",
            }
        target = "skipped" if dec["decision"] == "skip" else "completed"
        checkpoint_record = {
            "type": ct,
            "decision": dec["decision"],
            "approved_by": "auto" if auto_approve else "user",
            "at": _now(),
        }
    else:
        target = "completed"

    # 5. 原子写终态 + 审计字段(消费 receipt:一次性防重放)
    state["stages"][stage_id]["state"] = target
    state["stages"][stage_id]["outputs"] = outputs
    state["stages"][stage_id]["receipt"] = receipt
    state["stages"][stage_id]["checkpoint"] = checkpoint_record
    state["stages"][stage_id]["evidence"] = evidence
    state["stages"][stage_id]["completed_at"] = _now()
    state["stages"][stage_id]["updated_at"] = _now()
    state["current_stage"] = stage_id
    write_state(sf, state)
    consume_receipt(sf, stage_id)
    return {"ok": True, "stage": stage_id, "status": target, "checkpoint": checkpoint_record}


def skip_stage(
    state_file: Path | str,
    stage_id: str,
    *,
    reason: str,
    approved_by: str,
    receipt: Optional[dict] = None,
    evidence: Optional[List[dict]] = None,
) -> dict:
    """显式跳过(pending/running → skipped)。

    mandatory_review 阶段跳过必须提供 reason 与 approved_by(人工批准);
    所有 required_stages 中的阶段仍要求合法 receipt。
    """
    sf = Path(state_file)
    state = read_state(sf)
    _check_stage(state, stage_id)
    fsm = WorkflowFSM()
    current = state["stages"][stage_id]["state"]
    if current not in ("pending", "running"):
        raise TransitionError(f"阶段 {stage_id} 当前状态 {current} 不能 skip")

    ok_prereq, waiting = fsm.all_prereqs_completed(stage_id, _stage_states(state))
    if not ok_prereq:
        raise TransitionError(f"阶段 {stage_id} 前置未就绪: {waiting}", [f"prereq_not_ready: {waiting}"])

    ct = fsm.checkpoint_type(stage_id)
    if ct == "mandatory_review" and not (reason and approved_by):
        raise TransitionError(
            f"mandatory_review 阶段 {stage_id} 跳过必须提供 reason 与 approved_by",
            ["mandatory_skip_requires_approval"],
        )

    problems: List[str] = []
    policy = load_policy()
    if stage_id in policy.get("required_stages", []):
        if not receipt:
            problems.append(f"阶段 {stage_id} 缺少 dispatch receipt(委派 fail-closed)")
        else:
            # skip 无产出,不做 required_outputs 校验;但结构/subagent/登记三项必查
            from lib.delegation import (
                validate_receipt,
                validate_receipt_registered,
                validate_subagent_match,
            )
            if not validate_receipt(receipt, stage_id):
                problems.append(f"receipt 无效或与阶段不匹配({stage_id})")
            subagent_reason = validate_subagent_match(stage_id, receipt, policy)
            if subagent_reason:
                problems.append(subagent_reason)
            reg_reason = validate_receipt_registered(state, stage_id, receipt)
            if reg_reason:
                problems.append(reg_reason)
    if problems:
        raise TransitionError(f"阶段 {stage_id} 门控未通过: {'; '.join(problems)}", problems)

    state["stages"][stage_id]["state"] = "skipped"
    state["stages"][stage_id]["outputs"] = {
        "skip_reason": reason,
        "approved_by": approved_by,
    }
    state["stages"][stage_id]["receipt"] = receipt
    state["stages"][stage_id]["skip"] = {"reason": reason, "approved_by": approved_by, "at": _now()}
    state["stages"][stage_id]["evidence"] = evidence or []
    state["stages"][stage_id]["completed_at"] = _now()
    state["stages"][stage_id]["updated_at"] = _now()
    state["current_stage"] = stage_id
    write_state(sf, state)
    consume_receipt(sf, stage_id)
    return {"ok": True, "stage": stage_id, "state": "skipped"}


def fail_stage(state_file: Path | str, stage_id: str, *, reason: str = "") -> dict:
    """running → failed,记录失败原因。"""
    sf = Path(state_file)
    state = read_state(sf)
    _check_stage(state, stage_id)
    fsm = WorkflowFSM()
    current = state["stages"][stage_id]["state"]
    ok, nxt = fsm.validate_transition(current, "fail")
    if not ok:
        raise TransitionError(f"阶段 {stage_id} 当前状态 {current} 不能 fail")
    state["stages"][stage_id]["state"] = nxt.value
    state["stages"][stage_id]["error"] = {"reason": reason, "at": _now()}
    state["stages"][stage_id]["updated_at"] = _now()
    state["current_stage"] = stage_id
    write_state(sf, state)
    return {"ok": True, "stage": stage_id, "state": nxt.value}


def retry_stage(state_file: Path | str, stage_id: str) -> dict:
    """failed → running(重试)。"""
    sf = Path(state_file)
    state = read_state(sf)
    _check_stage(state, stage_id)
    fsm = WorkflowFSM()
    current = state["stages"][stage_id]["state"]
    ok, nxt = fsm.validate_transition(current, "retry")
    if not ok:
        raise TransitionError(f"阶段 {stage_id} 当前状态 {current} 不能 retry")
    state["stages"][stage_id]["state"] = nxt.value
    state["stages"][stage_id]["updated_at"] = _now()
    state["current_stage"] = stage_id
    write_state(sf, state)
    return {"ok": True, "stage": stage_id, "state": nxt.value}


def _parse_json(s: str):
    return json.loads(s)


def _load_json_opt(inline: Optional[str], file_path: Optional[str], name: str):
    """优先读文件(--xx-file),其次内联(--xx)。大 JSON 走文件,避免 shell 引号转义灾难。"""
    if file_path:
        try:
            return json.loads(Path(file_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise TransitionError(f"{name} 文件读取/解析失败({file_path}): {e}")
    return inline


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="唯一状态迁移入口(门控闭环)")
    sub = p.add_subparsers(dest="cmd")

    p_disp = sub.add_parser(
        "dispatch",
        help="一键委派:签发 receipt + 登记 + start(receipt 自动落盘 <state目录>/receipts/,并预校验角色匹配)",
    )
    p_disp.add_argument("state_file")
    p_disp.add_argument("stage")
    p_disp.add_argument("--subagent", required=True)
    p_disp.add_argument("--token", default="catpaw-orchestrator", help="签发方标识")
    p_disp.add_argument("--action", default="execute", choices=["execute", "skip"])

    p_hint = sub.add_parser("hint", help="下一步导航:当前可推进阶段 + 建议命令(只读)")
    p_hint.add_argument("state_file")

    p_reg = sub.add_parser("register", help="登记委派 receipt(防伪造,消费前必须登记)")
    p_reg.add_argument("state_file")
    p_reg.add_argument("--receipt", type=_parse_json, required=True)
    p_reg.add_argument("--receipt-file")

    p_start = sub.add_parser("start", help="pending → running(校验前置)")
    p_start.add_argument("state_file")
    p_start.add_argument("stage")

    p_complete = sub.add_parser("complete", help="完成阶段(产出/receipt/checkpoint 全门控)")
    p_complete.add_argument("state_file")
    p_complete.add_argument("stage")
    p_complete.add_argument("--outputs", type=_parse_json, default=None)
    p_complete.add_argument("--outputs-file")
    p_complete.add_argument("--receipt", type=_parse_json, default=None)
    p_complete.add_argument("--receipt-file")
    p_complete.add_argument("--checkpoint", choices=["approve", "skip", "revise"], default=None)
    p_complete.add_argument("--evidence", type=_parse_json, default=None)
    p_complete.add_argument("--evidence-file")
    p_complete.add_argument("--auto", action="store_true", help="自动批准 checkpoint(演示模式)")

    p_skip = sub.add_parser("skip", help="显式跳过(带批准)")
    p_skip.add_argument("state_file")
    p_skip.add_argument("stage")
    p_skip.add_argument("--reason", required=True)
    p_skip.add_argument("--approved-by", required=True)
    p_skip.add_argument("--receipt", type=_parse_json, default=None)
    p_skip.add_argument("--receipt-file")
    p_skip.add_argument("--evidence", type=_parse_json, default=None)
    p_skip.add_argument("--evidence-file")

    p_fail = sub.add_parser("fail", help="running → failed")
    p_fail.add_argument("state_file")
    p_fail.add_argument("stage")
    p_fail.add_argument("--reason", default="")

    p_retry = sub.add_parser("retry", help="failed → running")
    p_retry.add_argument("state_file")
    p_retry.add_argument("stage")

    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 1
    try:
        if args.cmd == "dispatch":
            from lib.delegation import issue_receipt, register_receipt
            sf = Path(args.state_file)
            receipt = issue_receipt(args.stage, args.subagent, args.token, action=args.action)
            # 预校验角色匹配:错误前置,附带 did-you-mean 提示
            mismatch = validate_subagent_match(args.stage, receipt)
            if mismatch:
                raise TransitionError(mismatch, [mismatch])
            receipts_dir = sf.parent / "receipts"
            receipts_dir.mkdir(parents=True, exist_ok=True)
            receipt_file = receipts_dir / f"receipt-{args.stage}.json"
            receipt_file.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            register_receipt(sf, receipt)
            start_res = start_stage(sf, args.stage)
            res = {
                "ok": True,
                "stage": args.stage,
                "receipt_file": str(receipt_file),
                "registered": True,
                "start": start_res,
            }
        elif args.cmd == "hint":
            res = hint(args.state_file)
        elif args.cmd == "register":
            from lib.delegation import register_receipt
            receipt = _load_json_opt(args.receipt, args.receipt_file, "--receipt")
            if receipt is None:
                raise TransitionError("register 需要 --receipt 或 --receipt-file")
            entry = register_receipt(args.state_file, receipt)
            res = {"ok": True, "stage": entry["receipt"]["stage"], "registered": True}
        elif args.cmd == "start":
            res = start_stage(args.state_file, args.stage)
        elif args.cmd == "complete":
            res = complete_stage(
                args.state_file, args.stage,
                outputs=_load_json_opt(args.outputs, args.outputs_file, "--outputs"),
                receipt=_load_json_opt(args.receipt, args.receipt_file, "--receipt"),
                checkpoint_decision=args.checkpoint,
                evidence=_load_json_opt(args.evidence, args.evidence_file, "--evidence"),
                auto_approve=args.auto,
            )
        elif args.cmd == "skip":
            res = skip_stage(
                args.state_file, args.stage,
                reason=args.reason, approved_by=args.approved_by,
                receipt=_load_json_opt(args.receipt, args.receipt_file, "--receipt"),
                evidence=_load_json_opt(args.evidence, args.evidence_file, "--evidence"),
            )
        elif args.cmd == "fail":
            res = fail_stage(args.state_file, args.stage, reason=args.reason)
        elif args.cmd == "retry":
            res = retry_stage(args.state_file, args.stage)
        else:
            p.print_help()
            return 1
    except TransitionError as e:
        print(json.dumps({"ok": False, "error": str(e), "reasons": e.reasons}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
