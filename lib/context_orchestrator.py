#!/usr/bin/env python3
"""上下文编排器:按阶段选择注入哪些知识 section + token 预算裁剪(对齐 super-assistant context_orchestrator)。

对接 build-repo-knowledge 的知识注入脚本:不同阶段注入不同 section,避免上下文稀释。
"""
from __future__ import annotations

from typing import Dict, List, Optional

# 阶段 → 需要注入的 section(对齐 skills/build-repo-knowledge 的按阶段注入映射)
STAGE_SECTIONS = {
    "1": ["agenda", "domain-model"],                                    # 需求分析 → 领域
    "2": ["agenda", "domain-model", "conventions"],                     # 契约设计
    "3": ["agenda", "architecture", "conventions", "domain-model"],     # 技术方案 → 全量
    "5A": ["agenda", "architecture", "conventions", "domain-model"],    # 后端实现 → 全量
    "5B": ["agenda", "architecture", "conventions", "domain-model"],    # 前端实现 → 全量
    "6": ["agenda", "architecture", "domain-model"],                    # 一致性校验
    "7": ["agenda", "conventions"],                                     # 评审 → 规范
    "8": ["agenda", "domain-model", "test-examples"],                   # 测试用例 → 领域+测试
    "9": ["agenda"],                                                    # 部署
    "10": ["agenda"],                                                   # 交付
}

DEFAULT_SECTIONS = ["agenda"]


def select_sections(stage: str) -> List[str]:
    """返回某阶段需要注入的 section 列表。"""
    return STAGE_SECTIONS.get(stage, DEFAULT_SECTIONS)


def estimate_tokens(text: str) -> int:
    """粗略 token 估算(中文按字符,英文按词;保守起见字符数/2)。"""
    return max(1, len(text) // 2)


def budget_context(sections: List[dict], max_tokens: int) -> List[dict]:
    """按 token 预算裁剪 sections。

    sections: [{name, text, priority}] (priority 越小越优先保留)。
    返回按优先级保留下来的 sections(累计 token 不超预算)。
    """
    ordered = sorted(sections, key=lambda s: s.get("priority", 99))
    kept = []
    used = 0
    for s in ordered:
        cost = estimate_tokens(s.get("text", ""))
        if used + cost > max_tokens:
            continue
        kept.append(s)
        used += cost
    return kept


def orchestrate(stage: str, sections: Dict[str, str], max_tokens: Optional[int] = None) -> str:
    """按阶段编排上下文:选 section + 预算裁剪,拼成一段上下文。"""
    names = select_sections(stage)
    items = [{"name": n, "text": sections.get(n, ""), "priority": i} for i, n in enumerate(names) if sections.get(n)]
    if max_tokens:
        items = budget_context(items, max_tokens)
    return "\n\n".join(f"--- {i['name']} ---\n{i['text']}" for i in items)


if __name__ == "__main__":
    import json
    print(json.dumps({"stage 7 sections": select_sections("7"), "stage 3 sections": select_sections("3")}, ensure_ascii=False, indent=2))
