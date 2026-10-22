#!/usr/bin/env python3
"""依赖自愈:检测缺失依赖 → 给出安装建议 → (可选)自动安装(对齐 super-assistant env_self_heal)。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 依赖清单:name → {check(cmd or import), install, critical}
DEPENDENCIES = {
    "python3": {"check_cmd": "python3 --version", "install": "brew install python3", "critical": True},
    "pyyaml": {"check_import": "yaml", "install": "pip3 install pyyaml", "critical": True},
    "node": {"check_cmd": "node --version", "install": "brew install node", "critical": False},
}


def detect() -> List[dict]:
    """检测缺失依赖,返回 [{name, install, critical}]。"""
    missing = []
    for name, spec in DEPENDENCIES.items():
        ok = True
        if "check_cmd" in spec:
            ok = shutil.which(spec["check_cmd"].split()[0]) is not None
        elif "check_import" in spec:
            try:
                __import__(spec["check_import"])
            except ImportError:
                ok = False
        if not ok:
            missing.append({"name": name, "install": spec["install"], "critical": spec["critical"]})
    return missing


def heal(auto_install: bool = False) -> dict:
    """检测 + 给出可行动的安装建议(fail-fast 风格)。

    安全决策:不自动安装。openclaw/agent 场景下 shell=True 执行安装命令是
    不可控执行面(开源项目危险默认值);缺什么就报什么 + 给出安装命令,
    由人决定是否执行。保留 auto_install 参数仅为兼容旧签名,恒等于 False。
    """
    missing = detect()
    if not missing:
        return {"ok": True, "missing": [], "suggestion": "",
                "install_commands": {}}
    critical_missing = [d for d in missing if d["critical"]]
    return {
        "ok": not critical_missing,
        "missing": missing,
        "suggestion": "请安装: " + ", ".join(d["name"] for d in missing),
        "install_commands": {d["name"]: d["install"] for d in missing},
    }


if __name__ == "__main__":
    print(json.dumps(heal(), ensure_ascii=False, indent=2))
