#!/usr/bin/env python3
"""委派协议(设计文档 §15):dispatch receipt 签发与 fail-closed 校验。

fail-closed:任何一条不满足(阶段必需 / receipt 有效 / subagent 匹配 / 产出完整)即阻断,
防止 AI 跳过必需阶段或伪造执行。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from lib.workflow_fsm import WorkflowFSM

RECEIPT_SCHEMA = "stage-subagent/v1"
POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "delegation-policy.json"


def load_policy(path: Optional[str | Path] = None) -> dict:
    p = Path(path) if path else POLICY_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def issue_receipt(stage_id: str, subagent: str, token: str) -> dict:
    """签发 dispatch receipt。token 由调用方(主 Agent)持有并回传。"""
    return {
        "schema": RECEIPT_SCHEMA,
        "stage": stage_id,
        "subagent": subagent,
        "token": token,
    }


def validate_receipt(receipt: Optional[dict], stage_id: str) -> bool:
    return bool(
        receipt
        and receipt.get("schema") == RECEIPT_SCHEMA
        and receipt.get("stage") == stage_id
        and receipt.get("subagent")
    )


def validate_dispatch(
    stage_id: str,
    receipt: Optional[dict],
    outputs: Optional[dict],
    policy: Optional[dict] = None,
) -> dict:
    """fail-closed 委派校验。返回 {"ok": bool, "reasons": [...]}。"""
    policy = policy if policy is not None else load_policy()
    reasons: List[str] = []

    # 1. 阶段必需
    required = policy.get("required_stages", [])
    if required and stage_id not in required:
        reasons.append(f"阶段 {stage_id} 不在 required_stages 中")

    # 2. receipt 有效且与阶段匹配
    if not validate_receipt(receipt, stage_id):
        reasons.append(f"receipt 无效或与阶段不匹配({stage_id})")

    # 3. subagent 匹配
    expected_sub = policy.get("stage_subagent", {}).get(stage_id)
    if receipt and expected_sub and receipt.get("subagent") != expected_sub:
        reasons.append(f"subagent 不匹配:期望 {expected_sub},实际 {receipt.get('subagent')}")

    # 4. outputs 满足 required_outputs
    fsm = WorkflowFSM()
    ok, missing = fsm.validate_completion(stage_id, outputs or {})
    if not ok:
        reasons.append(f"缺少必需产出: {missing}")

    return {"ok": not reasons, "reasons": reasons}
