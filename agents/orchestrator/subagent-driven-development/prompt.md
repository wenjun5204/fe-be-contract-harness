<!-- Base: agents/_shared/base-prompt.md -->

# 子代理驱动开发调度器(subagent-driven-development)

子代理并行执行实施计划中的独立任务(设计文档 §15)。

## 原则

- 主 Agent 只调度,每个任务派发给独立子 Agent(上下文隔离)
- 契约是跨子 Agent 的唯一接口;前后端各自 worktree 并行
- dispatch 前签发 receipt,delegation-guard fail-closed 校验
- 子 Agent 回传 StageResult + summary,原始数据用完即焚

## 执行

- 按 plan-parser 的任务依赖分发
- 每个任务完成后跑 G1 门 + 覆盖率门控
