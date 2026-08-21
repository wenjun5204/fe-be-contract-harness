#!/usr/bin/env python3
"""runner 自测。运行:python3 tests/test_runner.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.runner import run  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "petstore.yaml"


def test_run():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gen"
        state = Path(d) / "state.json"
        r = run(EXAMPLE, out, state, ["node", "react"])
        assert r["ok"], r
        # 确定性阶段完成(0,1,2,5A,5B,6,10)
        assert r["summary"]["done"] >= 7, r["summary"]
        # codegen 产物真实落盘
        assert (out / "node" / "codegen-manifest.json").exists()
        assert (out / "react" / "codegen-manifest.json").exists()
        # LLM 阶段签发委派指令
        agent_stages = {e["stage"] for e in r["events"] if e["kind"] == "agent"}
        assert agent_stages == {"3", "4", "7", "8", "9"}, agent_stages
        # 状态文件可续跑
        assert state.exists()


def main():
    test_run()
    print("OK: runner 自测通过")


if __name__ == "__main__":
    main()
