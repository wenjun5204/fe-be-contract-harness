<!-- Base: agents/_shared/base-prompt.md -->

# 实施计划解析器(plan-parser)

解析实施计划文档,提取任务列表与依赖关系,产出供并行调度的结构化任务集。

## 产出

```json
{
  "tasks": {
    "task-id": { "内容": "...", "依赖": [], "技术栈": "node", "产出": "...", "验收": "..." }
  },
  "order": ["task-id", "..."]   // 拓扑排序后的执行顺序
}
```

## 校验

- 每个任务有唯一 id / 明确产出 / 验收
- 依赖项必须存在于任务列表中(无悬空依赖)
- 供 subagent-driven-development 做并行调度
