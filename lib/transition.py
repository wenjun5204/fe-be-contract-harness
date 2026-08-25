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
    python3 lib/transition.py register <state> --receipt <json>           # 登记委派 receipt(防伪造)
    python3 lib/transition.py start <state> <stage>
    python3 lib/transition.py complete <state> <stage> --outputs <json> --receipt <json> [--checkpoint approve|skip] [--evidence <json>] [--auto]
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
from lib.delegation import consume_receipt, load_policy, validate_dispatch
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
    return {"ok": True, "stage": stage_id, "state": nxt.value}


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

    outputs = outputs or {}
    evidence = evidence or []
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

    if problems:
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
            from lib.delegation import validate_receipt, validate_receipt_registered
            if not validate_receipt(receipt, stage_id):
                problems.append(f"receipt 无效或与阶段不匹配({stage_id})")
            expected_sub = policy.get("stage_subagent", {}).get(stage_id)
            if expected_sub and receipt.get("subagent") != expected_sub:
                problems.append(f"subagent 不匹配:期望 {expected_sub},实际 {receipt.get('subagent')}")
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


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="唯一状态迁移入口(门控闭环)")
    sub = p.add_subparsers(dest="cmd")

    p_reg = sub.add_parser("register", help="登记委派 receipt(防伪造,消费前必须登记)")
    p_reg.add_argument("state_file")
    p_reg.add_argument("--receipt", type=_parse_json, required=True)

    p_start = sub.add_parser("start", help="pending → running(校验前置)")
    p_start.add_argument("state_file")
    p_start.add_argument("stage")

    p_complete = sub.add_parser("complete", help="完成阶段(产出/receipt/checkpoint 全门控)")
    p_complete.add_argument("state_file")
    p_complete.add_argument("stage")
    p_complete.add_argument("--outputs", type=_parse_json, default=None)
    p_complete.add_argument("--receipt", type=_parse_json, default=None)
    p_complete.add_argument("--checkpoint", choices=["approve", "skip", "revise"], default=None)
    p_complete.add_argument("--evidence", type=_parse_json, default=None)
    p_complete.add_argument("--auto", action="store_true", help="自动批准 checkpoint(演示模式)")

    p_skip = sub.add_parser("skip", help="显式跳过(带批准)")
    p_skip.add_argument("state_file")
    p_skip.add_argument("stage")
    p_skip.add_argument("--reason", required=True)
    p_skip.add_argument("--approved-by", required=True)
    p_skip.add_argument("--receipt", type=_parse_json, default=None)
    p_skip.add_argument("--evidence", type=_parse_json, default=None)

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
        if args.cmd == "register":
            from lib.delegation import register_receipt
            entry = register_receipt(args.state_file, args.receipt)
            res = {"ok": True, "stage": entry["receipt"]["stage"], "registered": True}
        elif args.cmd == "start":
            res = start_stage(args.state_file, args.stage)
        elif args.cmd == "complete":
            res = complete_stage(
                args.state_file, args.stage,
                outputs=args.outputs, receipt=args.receipt,
                checkpoint_decision=args.checkpoint, evidence=args.evidence,
                auto_approve=args.auto,
            )
        elif args.cmd == "skip":
            res = skip_stage(
                args.state_file, args.stage,
                reason=args.reason, approved_by=args.approved_by,
                receipt=args.receipt, evidence=args.evidence,
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
