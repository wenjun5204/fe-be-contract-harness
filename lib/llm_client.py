#!/usr/bin/env python3
"""LLM 客户端适配层 —— 统一 chat(messages, tools) 接口,屏蔽具体运行时。

两个实现:
- OpenAICompatClient:OpenAI 兼容 /chat/completions(纯 stdlib urllib,无三方依赖)。
  配置来源:构造参数 > 环境变量(OPENAI_BASE_URL / OPENAI_API_KEY / HARNESS_LLM_MODEL)。
- MockLLMClient:脚本驱动的确定性假客户端(测试/演示)。脚本为 assistant 步骤列表,
  每步是 {"tool_calls": [{"name", "arguments"}]} 或 {"content": "..."}。

响应统一规范化为:
    {"content": str | None, "tool_calls": [{"id", "name", "arguments": dict}]}

主循环(lib/llm_dispatch)只依赖该规范形状,不感知具体运行时。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Protocol

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class LLMError(RuntimeError):
    """运行时调用失败(配置缺失 / HTTP / 响应畸形 / 脚本耗尽)。"""


class LLMClient(Protocol):
    def chat(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict: ...


# ---- OpenAI 兼容实现 ----

def normalize_openai_message(message: dict) -> dict:
    """把 OpenAI 响应中的 message 规范化为 {"content", "tool_calls": [...]}。

    tool_calls[].function.arguments 是 JSON 字符串,这里反序列化为 dict;
    解析失败时置空 dict 并保留原始串,供模型自纠错。
    """
    tool_calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw_args = fn.get("arguments")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else {}
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        tool_calls.append({"id": tc.get("id"), "name": fn.get("name"), "arguments": args})
    return {"content": message.get("content"), "tool_calls": tool_calls}


class OpenAICompatClient:
    """OpenAI 兼容运行时客户端(标准库实现,支持任意兼容网关)。"""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 120,
    ):
        self.model = model or os.environ.get("HARNESS_LLM_MODEL", DEFAULT_MODEL)
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.timeout = timeout

    def chat(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        if not self.api_key:
            raise LLMError("缺少 OPENAI_API_KEY(或构造参数 api_key),无法调用 LLM 运行时")
        payload = {"model": self.model, "messages": messages, "tool_choice": "auto"}
        if tools:
            payload["tools"] = tools
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            raise LLMError(f"LLM 运行时 HTTP {e.code}: {body}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise LLMError(f"LLM 运行时不可达/响应畸形: {e}") from e
        try:
            return normalize_openai_message(data["choices"][0]["message"])
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"LLM 响应缺少 choices[0].message: {e}; body={str(data)[:300]}") from e


# ---- Mock 实现(脚本驱动) ----

def normalize_mock_step(step: dict, seq: int) -> dict:
    """校验并规范化 mock 脚本步骤为统一响应形状。"""
    if not isinstance(step, dict):
        raise LLMError(f"mock 脚本步骤 {seq} 必须是对象: {step!r}")
    tool_calls = []
    for i, tc in enumerate(step.get("tool_calls") or []):
        if not isinstance(tc, dict) or not tc.get("name"):
            raise LLMError(f"mock 脚本步骤 {seq} 的 tool_calls[{i}] 缺少 name: {tc!r}")
        args = tc.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError as e:
                raise LLMError(f"mock 脚本步骤 {seq} 的 tool_calls[{i}].arguments 不是合法 JSON: {e}") from e
        tool_calls.append({
            "id": tc.get("id") or f"mock-{seq}-{i}",
            "name": tc["name"],
            "arguments": args if isinstance(args, dict) else {},
        })
    if not tool_calls and not step.get("content"):
        raise LLMError(f"mock 脚本步骤 {seq} 需要 tool_calls 或非空 content: {step!r}")
    return {"content": step.get("content"), "tool_calls": tool_calls}


class MockLLMClient:
    """确定性 mock 运行时:按脚本顺序吐出 assistant 步骤,耗尽即抛错。"""

    def __init__(self, script: List[dict]):
        self._steps = [normalize_mock_step(s, i) for i, s in enumerate(script)]

    @classmethod
    def from_file(cls, path: str | Path) -> "MockLLMClient":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise LLMError(f"mock 脚本必须是步骤数组(JSON list): {path}")
        return cls(data)

    def chat(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        if not self._steps:
            raise LLMError("mock 脚本已耗尽(每轮 assistant 步骤需覆盖全部 tool calling 轮次)")
        return self._steps.pop(0)
