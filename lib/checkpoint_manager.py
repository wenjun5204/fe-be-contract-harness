#!/usr/bin/env python3
"""Checkpoint 管理器(设计文档 §10):人工卡点决策。

规则(与 super-assistant 一致):
- approve/confirm/ok/yes → approve
- skip → skip
- 其他文本(含空) → revise
- mandatory_review 不可 skip;artifact_review/optional 可 approve/skip/revise;none 无卡点。
"""
from __future__ import annotations

from typing import Optional

from lib.workflow_fsm import WorkflowFSM

APPROVE = "approve"
SKIP = "skip"
REVISE = "revise"

ALLOWED = {
    "mandatory_review": {APPROVE, REVISE},
    "artifact_review": {APPROVE, SKIP, REVISE},
    "optional": {APPROVE, SKIP, REVISE},
    "none": set(),
}


def checkpoint_type(stage_id: str) -> str:
    return WorkflowFSM().checkpoint_type(stage_id)


def requires_checkpoint(stage_id: str) -> bool:
    return checkpoint_type(stage_id) != "none"


def decide(stage_id: str, response: Optional[str]) -> dict:
    """把用户响应归一化为 approve/skip/revise,并校验是否被 checkpoint 类型允许。"""
    ct = checkpoint_type(stage_id)
    if ct == "none":
        return {"ok": True, "decision": None, "checkpoint": ct, "reason": None}

    resp = (response or "").strip().lower()
    if resp in ("approve", "confirm", "ok", "yes"):
        decision = APPROVE
    elif resp == "skip":
        decision = SKIP
    else:
        decision = REVISE

    allowed = ALLOWED.get(ct, set())
    ok = decision in allowed
    return {
        "ok": ok,
        "decision": decision,
        "checkpoint": ct,
        "reason": None if ok else f"{ct} 不允许 {decision}(仅允许 {sorted(allowed)})",
    }
