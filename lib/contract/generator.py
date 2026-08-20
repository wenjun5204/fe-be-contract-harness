#!/usr/bin/env python3
"""生成编排:契约 → 指定技术栈的代码文件集合。"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from lib.contract.parser import parse_contract
from lib.stack.adapter import get_adapter


def generate(contract_path: str | Path, stack_name: str) -> Dict[str, str]:
    """契约 + 技术栈 → {相对路径: 文件内容}(含 codegen-manifest.json)。"""
    model = parse_contract(contract_path)
    adapter = get_adapter(stack_name)
    return {f.path: f.content for f in adapter.generate(model)}


def write_out(contract_path: str | Path, stack_name: str, out_dir: str | Path) -> List[str]:
    """生成并落盘到 out_dir,返回写入的相对路径列表。"""
    files = generate(contract_path, stack_name)
    out = Path(out_dir)
    for rel, content in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return sorted(files.keys())
