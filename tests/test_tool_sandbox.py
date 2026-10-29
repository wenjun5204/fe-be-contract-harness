#!/usr/bin/env python3
"""执行类工具沙箱自测(P2-5):白名单 + 无 shell + 超时 + 输出截断。

用假栈 adapter(注入 _REGISTRY,用后恢复)驱动真实 subprocess,验证:
- 成功/失败退出码如实返回(ok 与 exit_code,可作 evidence)
- 超时被 kill(限时命令 + 短 timeout)
- 输出截断(头尾保留,中间省略并注明)
- 白名单命令含 shell 元字符 → 拒绝执行(SandboxError,fail-closed)
- 工具层接线:run_check 经 tool_registry 执行,错误收敛为 ok=false

运行:python3 tests/test_tool_sandbox.py
"""
import contextlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lib.stack.adapter as stack_adapter  # noqa: E402
from lib.tool_registry import build_default_tools  # noqa: E402
from lib.tool_sandbox import SandboxError, run_whitelisted  # noqa: E402


@contextlib.contextmanager
def _fake_stack(stack: str, *, lint=(), build=(), test=()):
    """把假 adapter 注入 _REGISTRY(用后恢复原 adapter)。"""
    stack_adapter._load_builtin()
    saved = stack_adapter._REGISTRY[stack]

    class _Fake:
        def lint_commands(self):
            return list(lint)

        def build_commands(self):
            return list(build)

        def test_commands(self):
            return list(test)

    stack_adapter._REGISTRY[stack] = _Fake
    try:
        yield
    finally:
        stack_adapter._REGISTRY[stack] = saved


def test_success_exit_code_zero():
    with tempfile.TemporaryDirectory() as d, _fake_stack("node", test=["true"]):
        res = run_whitelisted("test", "node", workdir=d)
        assert res["ok"], res
        assert res["exit_code"] == 0
        assert res["results"][0]["exit_code"] == 0
        assert "duration_seconds" in res


def test_nonzero_exit_reported():
    with tempfile.TemporaryDirectory() as d, _fake_stack("node", test=["false"]):
        res = run_whitelisted("test", "node", workdir=d)
        assert not res["ok"], res
        assert res["exit_code"] == 1, res  # 失败如实返回,可作失败证据
        assert res["results"][0]["exit_code"] == 1


def test_timeout_killed():
    with tempfile.TemporaryDirectory() as d, _fake_stack("node", test=["sleep 30"]):
        res = run_whitelisted("test", "node", workdir=d, timeout=1)
        assert not res["ok"], res
        assert res["results"][0]["timeout"], res["results"][0]
        assert "被 kill" in res["results"][0]["error"]


def test_output_truncated_head_and_tail():
    marker_head, marker_tail = "HEAD_MARKER", "TAIL_MARKER"
    # 注意:白名单命令不允许 shell 元字符(含 ;),脚本用 + 拼接
    script = f"print('{marker_head}'+'x'*20000+'{marker_tail}')"
    with tempfile.TemporaryDirectory() as d, _fake_stack("node", test=[f"python3 -c {script}"]):
        res = run_whitelisted("test", "node", workdir=d)
        out = res["results"][0]
        assert out["truncated"], out
        assert marker_head in out["output"] and marker_tail in out["output"], out["output"][:100]
        assert "elided" in out["output"]
        assert "x" * 20000 not in out["output"]  # 中间被省略


def test_whitelist_command_with_shell_metachar_rejected():
    """白名单命令含 shell 元字符(数据被篡改形态)→ 拒绝执行,不走 subprocess。"""
    with tempfile.TemporaryDirectory() as d, _fake_stack("node", test=["echo a && echo b"]):
        try:
            run_whitelisted("test", "node", workdir=d)
            assert False, "含元字符的白名单命令应被拒绝"
        except SandboxError as e:
            assert "元字符" in str(e), e


def test_empty_whitelist_is_soft_failure():
    """栈未配置该类命令 → 正常返回错误(交回模型),不抛异常。"""
    with tempfile.TemporaryDirectory() as d, _fake_stack("node", test=[]):
        res = run_whitelisted("test", "node", workdir=d)
        assert not res["ok"] and "无 test 白名单命令" in res["error"], res


def test_run_check_tool_via_registry():
    """工具层接线:run_check 参数无命令字段(schema 限 kind/stack/timeout),错误收敛 ok=false。"""
    with tempfile.TemporaryDirectory() as d, _fake_stack("node", test=["true"]):
        tools = build_default_tools(workdir=d)
        res = tools.execute("run_check", {"kind": "test", "stack": "node"})
        assert res["ok"], res

        # 失败命令 → ok=false 交回模型自纠错(不炸主循环)
        with _fake_stack("node", test=["false"]):
            res = tools.execute("run_check", {"kind": "test", "stack": "node"})
            assert not res["ok"] and res["exit_code"] == 1, res

        # 非法 kind → 收敛为 ok=false(schema enum 之外的值到达沙箱即 SandboxError)
        res = tools.execute("run_check", {"kind": "rm -rf", "stack": "node"})
        assert not res["ok"] and "未知 kind" in res["error"], res

        # 缺必填参数 → 参数校验拦截
        res = tools.execute("run_check", {"stack": "node"})
        assert not res["ok"] and "缺少必填参数" in res["error"], res


def main():
    test_success_exit_code_zero()
    test_nonzero_exit_reported()
    test_timeout_killed()
    test_output_truncated_head_and_tail()
    test_whitelist_command_with_shell_metachar_rejected()
    test_empty_whitelist_is_soft_failure()
    test_run_check_tool_via_registry()
    print("OK: tool_sandbox 自测通过(7 组断言)")


if __name__ == "__main__":
    main()
