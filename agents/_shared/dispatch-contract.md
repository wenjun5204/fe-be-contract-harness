# 子 Agent 委派契约(dispatch-contract)

> 主 Agent 调度子 Agent 的契约模板(设计文档 §15)。主 Agent 只调度,不执行业务逻辑。

## StageInput 构建

1. 从 DAG `required_outputs` + 对应 agent.json `inputs` 派生命名参数
2. 值域校验:必需字段非空
3. 契约 `openapi.yaml` 路径作为跨阶段上下文注入

## 委派流程

1. 读本契约,构建 StageInput
2. 签发 dispatch_receipt(`schema=stage-subagent/v1, stage, subagent, token`)
3. dispatch 子 Agent(独立上下文)
4. 子 Agent 执行 → 写 state → 回传 StageResult
5. `delegation-guard` fail-closed 校验(阶段必需 / receipt 有效 / subagent 匹配 / 产出完整)
6. `stage-completed` 路由下一阶段

## StageResult 结构

```json
{
  "provenance": { "stage": "6", "subagent": "contract/consistency-checker", "receipt": "...", "hooks_executed": ["checkpoint-guard"] },
  "outputs": { "consistency_report": "..." },
  "summary": "..."
}
```

## 隔离规则

- 主 Agent 只持 StageResult + summary,原始数据(代码/文档原文)用完即焚
- 契约是跨子 Agent 的**唯一接口**;前后端子 Agent 不直接通信
- 5A/5B 并行各自写 state,Stage 6 由 FSM 汇合校验
