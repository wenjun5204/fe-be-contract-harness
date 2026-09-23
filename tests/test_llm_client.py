#!/usr/bin/env python3
"""LLM Client 适配层自测。运行:python3 tests/test_llm_client.py"""
import json
import os
import sys
import tempfile
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.llm_client import (  # noqa: E402
    LLMError,
    MockLLMClient,
    normalize_mock_step,
    normalize_openai_message,
    OpenAICompatClient,
)


def test_normalize_openai_message():
    msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "read_contract", "arguments": '{"path": "api.yaml"}'}},
            {"id": "call_2", "type": "function",
             "function": {"name": "report_outputs", "arguments": '{"outputs": {"test_cases": []}}'}},
        ],
    }
    res = normalize_openai_message(msg)
    assert res["content"] is None
    assert res["tool_calls"][0] == {"id": "call_1", "name": "read_contract", "arguments": {"path": "api.yaml"}}
    assert res["tool_calls"][1]["arguments"]["outputs"] == {"test_cases": []}


def test_normalize_bad_arguments():
    msg = {"tool_calls": [{"id": "c", "function": {"name": "x", "arguments": "不是JSON"}}]}
    res = normalize_openai_message(msg)
    assert res["tool_calls"][0]["arguments"] == {}
    # 空字符串 / 非 dict 均兜底
    assert normalize_openai_message({"tool_calls": [{"function": {"name": "x", "arguments": ""}}]})["tool_calls"][0]["arguments"] == {}
    assert normalize_openai_message({}) == {"content": None, "tool_calls": []}


def test_mock_client_sequence():
    client = MockLLMClient([
        {"tool_calls": [{"name": "read_contract", "arguments": {}}]},
        {"content": "done"},
    ])
    r1 = client.chat([{"role": "user", "content": "go"}])
    assert r1["tool_calls"][0]["name"] == "read_contract"
    r2 = client.chat([])
    assert r2["content"] == "done" and r2["tool_calls"] == []
    try:
        client.chat([])
        raise AssertionError("脚本耗尽应抛 LLMError")
    except LLMError as e:
        assert "耗尽" in str(e)


def test_mock_step_validation():
    assert normalize_mock_step({"content": "hi"}, 0)["content"] == "hi"
    # arguments 支持 JSON 字符串形式
    step = normalize_mock_step({"tool_calls": [{"name": "x", "arguments": '{"a": 1}'}]}, 1)
    assert step["tool_calls"][0]["arguments"] == {"a": 1}
    # 缺 name / 空步骤 → 拒绝
    for bad in ([{"tool_calls": [{"arguments": {}}]}], [{"foo": 1}], ["str"]):
        try:
            normalize_mock_step(bad[0], 0)
            raise AssertionError(f"应当拒绝: {bad[0]!r}")
        except LLMError:
            pass


def test_mock_from_file():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "script.json"
        p.write_text(json.dumps([{"content": "ok"}]), encoding="utf-8")
        client = MockLLMClient.from_file(p)
        assert client.chat([])["content"] == "ok"
        # 非 list 脚本拒绝
        p.write_text(json.dumps({"stages": {}}), encoding="utf-8")
        try:
            MockLLMClient.from_file(p)
            raise AssertionError("非数组脚本应拒绝")
        except LLMError:
            pass


def test_openai_missing_key():
    env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY",)}
    with unittest.mock.patch.dict(os.environ, env, clear=True):
        client = OpenAICompatClient()
        try:
            client.chat([{"role": "user", "content": "hi"}])
            raise AssertionError("缺 key 应抛 LLMError")
        except LLMError as e:
            assert "OPENAI_API_KEY" in str(e)


def test_openai_config_env():
    env = dict(os.environ)
    env.update({"OPENAI_BASE_URL": "http://localhost:9999/v1/", "HARNESS_LLM_MODEL": "test-model"})
    with unittest.mock.patch.dict(os.environ, env, clear=True):
        client = OpenAICompatClient()
        assert client.base_url == "http://localhost:9999/v1"
        assert client.model == "test-model"


def main():
    test_normalize_openai_message()
    test_normalize_bad_arguments()
    test_mock_client_sequence()
    test_mock_step_validation()
    test_mock_from_file()
    test_openai_missing_key()
    test_openai_config_env()
    print("OK: llm_client 自测通过(7 组断言)")


if __name__ == "__main__":
    main()
