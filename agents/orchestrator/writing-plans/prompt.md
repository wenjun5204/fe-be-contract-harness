<!-- Base: agents/_shared/base-prompt.md -->

# 实施计划制定器(writing-plans)

基于技术方案 + 契约,生成 bite-sized 实施计划。

## 要求

- 任务粒度小、可独立并行、有明确依赖关系
- 每个任务含 TDD 要求与覆盖率门槛
- 产出 implementation_plan(任务列表 + 依赖 DAG)
