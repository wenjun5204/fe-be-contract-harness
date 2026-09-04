#!/usr/bin/env python3
"""委派协议(设计文档 §15):dispatch receipt 签发、登记、消费与 fail-closed 校验。

fail-closed:任何一条不满足(阶段必需 / receipt 有效 / subagent 匹配 / 产出完整)即阻断,
防止 AI 跳过必需阶段或伪造执行。

第一阶段补强(防伪造):
- 签发后的 receipt 必须登记到 state.json 的 receipts 表(token 防伪,仅登记表内可校验通过)
- 消费(complete/skip 终态)后标记 used,一次性使用,防重放
- validate_dispatch(state_file=...) 时叠加登记校验;不传 state_file 保持纯函数(兼容低层调用)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from lib.workflow_fsm import WorkflowFSM

RECEIPT_SCHEMA = "stage-subagent/v1"
POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "delegation-policy.json"


def load_policy(path: Optional[str | Path] = None) -> dict:
    p = Path(path) if path else POLICY_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _as_subagent_list(value: object) -> List[str]:
    """将 receipt 或策略中的单/多 Agent 表示规范化为非空列表。"""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    return []


def receipt_subagents(receipt: Optional[dict]) -> List[str]:
    """读取 receipt 承载的执行 Agent，兼容 v1 的单 `subagent` 字段。"""
    if not receipt:
        return []
    return _as_subagent_list(receipt.get("subagents") or receipt.get("subagent"))


def resolve_subagents(
    stage_id: str,
    stacks: Optional[Iterable[str]] = None,
    policy: Optional[dict] = None,
    for_skip: bool = False,
) -> List[str]:
    """按阶段及实际技术栈解析执行 Agent。

    普通阶段使用字符串配置；代码生成阶段使用 `by_stack` 映射。未传 stacks 时，
    仅允许解析静态阶段，避免把候选 Agent 误当作实际执行者。
    """
    policy = policy if policy is not None else load_policy()
    configured = policy.get("stage_subagent", {}).get(stage_id)
    if isinstance(configured, str):
        return [configured]
    if not isinstance(configured, dict):
        return []
    if for_skip:
        return _as_subagent_list(configured.get("skip_subagent"))
    by_stack = configured.get("by_stack", {})
    return [by_stack[stack] for stack in (stacks or []) if stack in by_stack]


def allowed_subagents(stage_id: str, policy: Optional[dict] = None) -> List[str]:
    """返回策略允许的 Agent 集合，供 receipt fail-closed 校验使用。"""
    policy = policy if policy is not None else load_policy()
    configured = policy.get("stage_subagent", {}).get(stage_id)
    if isinstance(configured, str):
        return [configured]
    if isinstance(configured, dict):
        # 允许集合 = by_stack 候选 + skip 候选(去重保序);dict_values 需先转 list 再规范化
        candidates = list(configured.get("by_stack", {}).values()) + _as_subagent_list(configured.get("skip_subagent"))
        return list(dict.fromkeys(candidates))
    return _as_subagent_list(configured)


def issue_receipt(
    stage_id: str,
    subagent: Union[str, List[str]],
    token: str,
    action: str = "execute",
) -> dict:
    """签发 dispatch receipt，支持一个阶段由多个实际栈 Agent 共同执行。"""
    subagents = _as_subagent_list(subagent)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "stage": stage_id,
        "subagent": subagents[0] if len(subagents) == 1 else None,
        "token": token,
        "action": action,
    }
    if len(subagents) > 1:
        receipt["subagents"] = subagents
    return receipt


def validate_receipt(receipt: Optional[dict], stage_id: str) -> bool:
    return bool(
        receipt
        and receipt.get("schema") == RECEIPT_SCHEMA
        and receipt.get("stage") == stage_id
        and receipt_subagents(receipt)
    )


def suggest_subagents(actual: List[str], allowed: List[str]) -> List[str]:
    """对不匹配的 Agent 名给出最接近的候选(did-you-mean,降低角色名不可发现的摩擦)。"""
    import difflib
    suggestions: List[str] = []
    for name in actual:
        suggestions.extend(difflib.get_close_matches(name, allowed, n=2, cutoff=0.4))
    return list(dict.fromkeys(suggestions))


def validate_subagent_match(stage_id: str, receipt: Optional[dict], policy: Optional[dict] = None) -> Optional[str]:
    """校验 receipt 中的实际 Agent 与阶段动作及策略匹配。"""
    policy = policy if policy is not None else load_policy()
    actual = receipt_subagents(receipt)
    configured = policy.get("stage_subagent", {}).get(stage_id)
    if not actual or not configured:
        return None
    if isinstance(configured, dict):
        allowed = _as_subagent_list(
            configured.get("skip_subagent") if receipt.get("action") == "skip" else list(configured.get("by_stack", {}).values())
        )
    else:
        allowed = _as_subagent_list(configured)
    unexpected = sorted(set(actual) - set(allowed))
    if unexpected:
        hint = ""
        close = suggest_subagents(sorted(set(actual)), allowed)
        if close:
            hint = f";您是不是想用: {', '.join(close)}"
        return f"subagent 不匹配:阶段允许 {allowed},实际 {actual}{hint}"
    return None


# ---- 登记 / 消费 / 防伪 ----

def _load_state(state_file) -> dict:
    from lib.state_manager import read_state
    return read_state(Path(state_file))


def _save_state(state_file, state: dict) -> None:
    from lib.state_manager import write_state
    write_state(Path(state_file), state)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def register_receipt(state_file: str | Path, receipt: dict) -> dict:
    """把签发后的 receipt 登记到 state 的 receipts 表(幂等:同 stage+token 重复登记覆盖)。"""
    if not validate_receipt(receipt, receipt.get("stage", "")):
        raise ValueError(f"receipt 无效: {receipt}")
    state = _load_state(state_file)
    stage = receipt["stage"]
    state.setdefault("receipts", {})
    state["receipts"][stage] = {
        "receipt": receipt,
        "used": False,
        "registered_at": _now(),
        "consumed_at": None,
    }
    _save_state(state_file, state)
    return state["receipts"][stage]


def validate_receipt_registered(state: dict, stage_id: str, receipt: Optional[dict]) -> Optional[str]:
    """登记表校验:存在 / token 匹配 / 未消费。返回 None=通过,否则返回原因。"""
    table = state.get("receipts", {})
    entry = table.get(stage_id)
    if not entry:
        return f"阶段 {stage_id} 的 receipt 未登记(防伪造:必须先 register_receipt)"
    expected = entry.get("receipt", {})
    if receipt is None or receipt.get("token") != expected.get("token"):
        return f"阶段 {stage_id} 的 receipt token 与登记不符(疑似伪造)"
    if entry.get("used"):
        return f"阶段 {stage_id} 的 receipt 已被消费(一次性,禁止重放)"
    return None


def consume_receipt(state_file: str | Path, stage_id: str) -> None:
    """终态落盘后标记 receipt 已消费(一次性)。"""
    state = _load_state(state_file)
    entry = state.get("receipts", {}).get(stage_id)
    if entry:
        entry["used"] = True
        entry["consumed_at"] = _now()
        _save_state(state_file, state)


def validate_dispatch(
    stage_id: str,
    receipt: Optional[dict],
    outputs: Optional[dict],
    policy: Optional[dict] = None,
    state_file: Optional[str | Path] = None,
) -> dict:
    """fail-closed 委派校验。返回 {"ok": bool, "reasons": [...]}。

    传 state_file 时叠加登记表校验(防伪造 + 一次性);不传则仅做结构校验(低层纯函数)。
    """
    policy = policy if policy is not None else load_policy()
    reasons: List[str] = []

    # 1. 阶段必需
    required = policy.get("required_stages", [])
    if required and stage_id not in required:
        reasons.append(f"阶段 {stage_id} 不在 required_stages 中")

    # 2. receipt 有效且与阶段匹配
    if not validate_receipt(receipt, stage_id):
        reasons.append(f"receipt 无效或与阶段不匹配({stage_id})")

    # 3. subagent 匹配（动态阶段校验实际 Agent 是否在该阶段允许集合内）
    subagent_reason = validate_subagent_match(stage_id, receipt, policy)
    if subagent_reason:
        reasons.append(subagent_reason)

    # 4. 登记表校验(防伪造 + 一次性)
    if state_file is not None and validate_receipt(receipt, stage_id):
        try:
            state = _load_state(state_file)
            reg_reason = validate_receipt_registered(state, stage_id, receipt)
            if reg_reason:
                reasons.append(reg_reason)
        except FileNotFoundError:
            reasons.append(f"state 文件不存在: {state_file}(无法校验 receipt 登记)")

    # 5. outputs 满足 required_outputs
    fsm = WorkflowFSM()
    ok, missing = fsm.validate_completion(stage_id, outputs or {})
    if not ok:
        reasons.append(f"缺少必需产出: {missing}")

    return {"ok": not reasons, "reasons": reasons}
