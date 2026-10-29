"""平台适配层:平台原始事件 → hook 标准 envelope;dispatch directive → 子 Agent 任务包。

- event_adapter.normalize      平台事件精确/尽力映射(hook_protocol --platform 入口)
- subagent_dispatch            子 Agent 派发与 StageResult 回传(经唯一 transition 门控)
- platform-adapter.sh          运行时平台探测(HARNESS_PLATFORM 显式覆盖优先)
"""
