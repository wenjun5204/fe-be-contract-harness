#!/usr/bin/env python3
"""StackAdapter 抽象接口 + 注册表。

技术栈适配层(设计文档 §4):把 React/Vue/Java/Node 的差异隔离在各自适配器内,
编排层(planner/consistency-checker)零栈感知。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class GeneratedFile:
    path: str
    content: str


class StackAdapter(ABC):
    name: str = ""
    kind: str = ""  # frontend | backend

    @abstractmethod
    def generate(self, model: dict) -> List[GeneratedFile]:
        """从规范化契约模型生成文件列表(含 codegen-manifest.json)。"""

    def manifest(self, routes: List[str], models: List[str]) -> GeneratedFile:
        """生成 codegen-manifest.json(供 G1 生成门做结构忠实性校验)。"""
        return GeneratedFile(
            "codegen-manifest.json",
            json.dumps(
                {"stack": self.name, "kind": self.kind, "routes": routes, "models": models},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )

    # 命令映射与项目识别(子类覆盖,设计文档 §4.2)
    LINT: List[str] = []
    BUILD: List[str] = []
    TEST: List[str] = []
    COVERAGE: str = ""
    MARKERS: List[str] = []
    DEPLOY: List[str] = []

    def lint_commands(self) -> List[str]:
        return list(self.LINT)

    def build_commands(self) -> List[str]:
        return list(self.BUILD)

    def test_commands(self) -> List[str]:
        return list(self.TEST)

    def coverage_command(self) -> str:
        return self.COVERAGE

    def detect(self, repo_path: str) -> dict:
        """基于标记文件做项目识别(最佳努力)。"""
        p = Path(repo_path)
        evidence = [m for m in self.MARKERS if (p / m).exists()]
        return {"stack": self.name, "kind": self.kind, "detected": bool(evidence), "evidence": evidence}

    def deploy_adapters(self) -> List[str]:
        """部署方式路由(static 前端静态产物 / container 后端服务容器)。"""
        return list(self.DEPLOY)


_REGISTRY: Dict[str, type] = {}


def register(cls):
    _REGISTRY[cls.name] = cls
    return cls


def _load_builtin() -> None:
    if not _REGISTRY:
        from lib.stack.expo.adapter import ExpoStackAdapter  # noqa: F401
        from lib.stack.java.adapter import JavaStackAdapter  # noqa: F401
        from lib.stack.node.adapter import NodeStackAdapter  # noqa: F401
        from lib.stack.react.adapter import ReactStackAdapter  # noqa: F401
        from lib.stack.react_native.adapter import ReactNativeStackAdapter  # noqa: F401
        from lib.stack.vue.adapter import VueStackAdapter  # noqa: F401


def get_adapter(name: str) -> StackAdapter:
    _load_builtin()
    if name not in _REGISTRY:
        raise KeyError(f"未知的 stack adapter: {name}")
    return _REGISTRY[name]()


def available() -> List[str]:
    _load_builtin()
    return sorted(_REGISTRY.keys())
