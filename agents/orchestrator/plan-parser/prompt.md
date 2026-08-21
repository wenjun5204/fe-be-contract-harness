<!-- Base: agents/_shared/base-prompt.md -->

# 实施计划解析器(plan-parser)

解析实施计划文档,提取任务列表与依赖关系。

## 产出

- tasks:{任务 id → 内容 / 依赖 / 技术栈 / 产出}
- 供 subagent-driven-development 做并行调度
