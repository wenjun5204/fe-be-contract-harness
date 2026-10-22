#!/usr/bin/env python3
"""生成编排:契约 → 指定技术栈的代码文件集合。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from lib.contract.parser import parse_contract
from lib.stack.adapter import get_adapter

MANIFEST_NAME = "codegen-manifest.json"


def content_sha256(content: str) -> str:
    """产物内容指纹(sha256,hex)。供 manifest 记录与 evidence 完整性校验。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def generate(contract_path: str | Path, stack_name: str) -> Dict[str, str]:
    """契约 + 技术栈 → {相对路径: 文件内容}(含 codegen-manifest.json)。"""
    model = parse_contract(contract_path)
    adapter = get_adapter(stack_name)
    return {f.path: f.content for f in adapter.generate(model)}


def write_out(contract_path: str | Path, stack_name: str, out_dir: str | Path) -> List[str]:
    """生成并落盘到 out_dir,返回写入的相对路径列表。

    P2-6 产物完整性:落盘后把每个产物(除 manifest 自身)的 sha256 写进
    codegen-manifest.json 的 artifacts 字段。后续 _validate_evidence /
    drift 检测可凭 hash 判断"产物存在"之外更关键的"内容未被篡改"。
    """
    files = generate(contract_path, stack_name)
    out = Path(out_dir)
    for rel, content in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # 追加产物 hash 到 manifest(改写后的 manifest 不计入自身 hash)
    manifest_path = out / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"] = {
        rel: content_sha256(content)
        for rel, content in files.items()
        if rel != MANIFEST_NAME
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return sorted(files.keys())


def verify_artifacts(out_dir: str | Path) -> Dict[str, List[str]]:
    """按 manifest.artifacts 校验落盘产物内容 hash。

    返回 {"tampered": [...], "missing": [...], "no_manifest": [...]}。
    兼容旧产物:manifest 无 artifacts 字段 → 返回 no_manifest,调用方降级处理。
    """
    out = Path(out_dir)
    manifest_path = out / MANIFEST_NAME
    if not manifest_path.is_file():
        return {"tampered": [], "missing": [], "no_manifest": [str(out)]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts") or {}
    if not artifacts:
        return {"tampered": [], "missing": [], "no_manifest": [str(out)]}
    tampered, missing = [], []
    for rel, expected in artifacts.items():
        p = out / rel
        if not p.is_file():
            missing.append(rel)
        elif content_sha256(p.read_text(encoding="utf-8")) != expected:
            tampered.append(rel)
    return {"tampered": tampered, "missing": missing, "no_manifest": []}
