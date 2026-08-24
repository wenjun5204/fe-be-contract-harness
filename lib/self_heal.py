#!/usr/bin/env python3
"""依赖自愈:检测缺失依赖 → 给出安装建议 → (可选)自动安装(对齐 super-assistant env_self_heal)。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

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
    """检测 + 自愈。auto_install=True 时尝试安装(薄封装)。"""
    missing = detect()
    if not missing:
        return {"ok": True, "missing": [], "installed": [], "suggestion": ""}
    installed = []
    for dep in missing:
        if auto_install:
            try:
                subprocess.run(dep["install"], shell=True, capture_output=True, timeout=120, check=False)
                installed.append(dep["name"])
            except Exception:
                pass
    critical_missing = [d for d in missing if d["critical"]]
    return {
        "ok": not critical_missing,
        "missing": missing,
        "installed": installed,
        "suggestion": "请安装: " + ", ".join(d["name"] for d in missing),
    }


if __name__ == "__main__":
    print(json.dumps(heal(), ensure_ascii=False, indent=2))
