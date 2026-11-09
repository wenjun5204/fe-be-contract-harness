#!/usr/bin/env python3
"""上下文编排器：为阶段派发构造按实体检索、按预算裁剪的知识上下文。"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

# 阶段 → 需要注入的 section；同一顺序也是预算不足时的优先级。
STAGE_SECTIONS = {
    "1": ["agenda", "business-knowledge", "qa-knowledge", "domain-model"],
    "2": ["agenda", "business-knowledge", "backend-knowledge", "frontend-knowledge", "domain-model", "conventions"],
    "3": ["agenda", "architecture", "conventions", "business-knowledge", "domain-model"],
    "5A": ["agenda", "architecture", "conventions", "business-knowledge", "backend-knowledge", "domain-model"],
    "5B": ["agenda", "architecture", "conventions", "business-knowledge", "frontend-knowledge", "domain-model"],
    "6": ["agenda", "architecture", "business-knowledge", "domain-model"],
    "7": ["agenda", "conventions", "business-knowledge"],
    "8": ["agenda", "business-knowledge", "qa-knowledge", "domain-model", "test-examples"],
    "9": ["agenda"],
    "10": ["agenda"],
}
DEFAULT_SECTIONS = ["agenda"]
DOMAIN_SECTION = {
    "business-knowledge": "business",
    "backend-knowledge": "backend",
    "frontend-knowledge": "frontend",
    "qa-knowledge": "qa",
}
REPO_SECTION_FILE = {
    "architecture": ".agents/docs/architecture.md",
    "conventions": ".agents/docs/conventions.md",
    "domain-model": ".agents/docs/domain-model.md",
    "test-examples": ".agents/test-examples",
}


def select_sections(stage: str) -> List[str]:
    return STAGE_SECTIONS.get(stage, DEFAULT_SECTIONS)


def estimate_tokens(text: str) -> int:
    """粗估 token 数:ASCII 段 ~4 字符/token,CJK 段 ~1 字符/token。

    len//2 对中文低估约一半(4000 预算实际注入近翻倍内容),对纯英文高估一倍。
    纯 ASCII 走 len//4;遇到 CJK 字符每字符计 1,保证预算不超发。
    """
    ascii_len = 0
    cjk = 0
    for ch in text:
        if ord(ch) > 0x2E80:  # CJK 及全角区
            cjk += 1
        else:
            ascii_len += 1
    return max(1, ascii_len // 4 + cjk)


def budget_context(sections: List[dict], max_tokens: int) -> List[dict]:
    """按照 priority 保留完整 section；不会截断规则，防止注入半条约定。"""
    ordered = sorted(sections, key=lambda item: item.get("priority", 99))
    kept, used = [], 0
    for section in ordered:
        cost = estimate_tokens(section.get("text", ""))
        if used + cost > max_tokens:
            continue
        kept.append(section)
        used += cost
    return kept


def orchestrate(stage: str, sections: Dict[str, str], max_tokens: Optional[int] = None) -> str:
    names = select_sections(stage)
    items = [{"name": name, "text": sections.get(name, ""), "priority": index} for index, name in enumerate(names) if sections.get(name)]
    if max_tokens:
        items = budget_context(items, max_tokens)
    return "\n\n".join(f"--- {item['name']} ---\n{item['text']}" for item in items)


def _declared_entities(entry: dict) -> set:
    """条目声明的实体名集合(entity 单值 + entities 列表,统一小写)。"""
    declared = set()
    if entry.get("entity"):
        declared.add(str(entry["entity"]).lower())
    for name in entry.get("entities") or []:
        if name:
            declared.add(str(name).lower())
    return declared


def _matches_entity(entry: dict, terms: Iterable[str]) -> bool:
    """实体精确集合交集(方案 B §3.4,替换子串 contains)。

    根因 #3 修复:旧子串匹配让 stripe 的 order_return 误命中 entity Order(双向误报)。
    收紧为精确比对后:全局层 order.md(entity=Order)只在契约真有 Order 实体时注入。
    - type=convention → 恒注入(跨实体工程约定;产品私有业务规则包也惯用此标签,
      但作用域层已把它圈在 products/<pid>/ 内,恒注入不再泄漏跨产品)
    - 条目未声明实体 / 契约未识别实体 → 不过滤(冷启动可用,fail-open 只在无信息面)
    """
    if entry.get("type") == "convention":
        return True
    declared = _declared_entities(entry)
    normalized = {term.lower() for term in terms if term}
    if not declared or not normalized:
        return True
    return bool(declared & normalized)


def _domain_text(domain: str, entities: List[str], warnings: List[str], product: Optional[str] = None) -> str:
    from lib.domain_knowledge import load_entries, render_entry
    try:
        entries = [
            entry for entry in load_entries(domain, product=product)
            if entry.get("status") == "confirmed" and _matches_entity(entry, entities)
        ]
    except (OSError, ValueError) as exc:
        warnings.append(f"无法加载 {domain} 领域知识: {exc}")
        return ""
    if not entries:
        return ""
    return "\n\n".join(render_entry(entry).strip() for entry in entries)


def _repo_text(repo: Path, section: str, warnings: List[str]) -> str:
    path = repo / REPO_SECTION_FILE[section]
    if section == "test-examples":
        if not path.is_dir():
            return ""
        files = sorted(path.glob("baseline/*.md")) + sorted(path.glob("delivery/*.md"))
        return "\n\n".join(file.read_text(encoding="utf-8") for file in files)
    if not path.exists():
        warnings.append(f"仓库知识缺少 {REPO_SECTION_FILE[section]}")
        return ""
    text = path.read_text(encoding="utf-8")
    if "待 build-repo-knowledge 生成" in text:
        warnings.append(f"仓库知识仍为占位符: {REPO_SECTION_FILE[section]}")
        return ""
    return text


def build_dispatch_context(
    stage: str,
    contract: str,
    entities: Optional[Iterable[str]] = None,
    repo: Optional[str | Path] = None,
    max_tokens: int = 4000,
    product: Optional[str] = None,
) -> dict:
    """构造可直接交给子 Agent 的上下文包。

    领域知识按契约 schema 名称与显式实体过滤；仓库知识只读取当前阶段需要的 section。
    缺少可选知识不会阻断派发，而会写入 warnings，保证冷启动可用。

    作用域隔离(方案 B):product=<pid> 时知识 = _global/ ∪ products/<pid>/;
    其他产品的知识物理上不读取。product=None(冷启动未解析)→ 仅 _global/。
    """
    entity_list = sorted({entity for entity in (entities or []) if entity})
    warnings: List[str] = []
    raw_sections: Dict[str, str] = {
        "agenda": f"stage={stage}; contract={contract}; entities={', '.join(entity_list) or '未从契约识别'}",
    }
    for section, domain in DOMAIN_SECTION.items():
        if section in select_sections(stage):
            raw_sections[section] = _domain_text(domain, entity_list, warnings, product)
    if repo:
        repo_path = Path(repo).expanduser().resolve()
        if not repo_path.is_dir():
            warnings.append(f"目标仓库不存在，跳过仓库知识: {repo_path}")
        else:
            for section in REPO_SECTION_FILE:
                if section in select_sections(stage):
                    raw_sections[section] = _repo_text(repo_path, section, warnings)
    items = [
        {"name": name, "text": raw_sections.get(name, ""), "priority": index}
        for index, name in enumerate(select_sections(stage)) if raw_sections.get(name)
    ]
    kept = budget_context(items, max_tokens)
    omitted = [item["name"] for item in items if item not in kept]
    return {
        "schema": "dispatch-context/v1",
        "stage": stage,
        "entities": entity_list,
        "product": product,
        "repo": str(Path(repo).expanduser().resolve()) if repo else None,
        "max_tokens": max_tokens,
        "estimated_tokens": sum(estimate_tokens(item["text"]) for item in kept),
        "sections": [{"name": item["name"], "text": item["text"], "estimated_tokens": estimate_tokens(item["text"])} for item in kept],
        "omitted_sections": omitted,
        "warnings": warnings,
        "text": "\n\n".join(f"--- {item['name']} ---\n{item['text']}" for item in kept),
    }


if __name__ == "__main__":
    import json
    print(json.dumps({"stage 7 sections": select_sections("7"), "stage 3 sections": select_sections("3")}, ensure_ascii=False, indent=2))
