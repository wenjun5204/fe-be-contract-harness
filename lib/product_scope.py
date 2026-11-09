#!/usr/bin/env python3
"""产品作用域解析 —— KB 作用域隔离(方案 B,docs/designs/kb-scope-isolation.md §3.3)。

解析链(run 启动时确定一次,结果固化进 state.json):
1. 显式 --product(人工命名,语义最清晰,真实项目推荐)
2. state.json 已固化的 product_id(重跑沿用;同产品改 title 不换 scope)
3. info.title 派生 slug(零配置冷启动;首跑解析后由 runner 固化)

三条都解析不出 → None(读侧只注入 _global/;写侧走 pending/ 兜底,绝不落 _global/)。
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# product_id 规范化:小写、非字母数字折叠为连字符、截断 64 字符(与 KB 目录名严格一致)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
MAX_PRODUCT_ID_LEN = 64


def slugify(text: str) -> str:
    """文本 → product_id slug;无法规范出有效字符时返回空串。"""
    if not text:
        return ""
    slug = _NON_ALNUM.sub("-", str(text).strip().lower()).strip("-")
    return slug[:MAX_PRODUCT_ID_LEN].rstrip("-")


def resolve_product_id(
    explicit: Optional[str] = None,
    contract_model: Optional[dict] = None,
    state: Optional[dict] = None,
) -> Tuple[Optional[str], str]:
    """返回 (product_id, source);source ∈ explicit / state / title / unresolved。"""
    if explicit:
        pid = slugify(explicit)
        if pid:
            return pid, "explicit"
    pinned = (state or {}).get("product_id")
    if pinned:
        return str(pinned), "state"
    title = ((contract_model or {}).get("info") or {}).get("title", "")
    pid = slugify(str(title or ""))
    if pid:
        return pid, "title"
    return None, "unresolved"
