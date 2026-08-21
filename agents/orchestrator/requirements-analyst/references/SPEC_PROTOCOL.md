# 结构化需求 Spec 协议(SPEC_PROTOCOL)

> 供 requirements-analyst 产出**机器可校验**的需求 Spec。确定性守卫在 `lib/requirements_spec.py`,由 workflow_fsm 在 Stage 1→2 时调用。

## 协议结构(JSON)

```json
{
  "schema_version": "1.0",
  "status": "scope_assessment | clarification | ready | approved",
  "scope": { "complexity": "L|M|H", "subsystems": [], "cross_team_dependencies": [] },
  "clarification": {
    "round": 0,
    "max_rounds": 3,
    "questions": [],
    "answers": [],
    "confirmed_facts": [{ "fact": "...", "source": "user|user_document|code|ai_inference" }],
    "assumptions": [],
    "unresolved_questions": [],
    "coverage": { "goal_value": "pending|covered", "...": "..." }
  },
  "contract_readiness": {
    "entities": [
      { "name": "Pet", "fields": [{ "name": "id", "type": "integer", "required": true, "bounds": null }], "states": [] }
    ],
    "error_codes": [{ "code": "404", "meaning": "not found" }]
  },
  "document": { "approved": false, "quality_gate": "pending|passed|failed" }
}
```

## 硬性约束(确定性守卫)

1. **澄清有界**:≤3 轮,每轮 3-5 问
2. **类别覆盖**:9 个高影响类必须 `covered`(goal_value / users_permissions / scope / main_flow / state / data / exceptions / dependencies / acceptance)
3. **事实有来源**:confirmed_facts 每条带 source
4. **质量门**:无占位符(TBD/待定)、无歧义词(按需/视情况/适当处理/必要时)
5. **契约就绪性**:至少 1 个实体 + 实体有字段 + 错误码已定义

## 为什么(与 markdown PRD 的本质区别)

| 维度 | markdown PRD | 结构化 Spec |
|------|-------------|-------------|
| 可机器校验 | ❌ 靠 LLM"读懂" | ✅ `validate_requirements_completion` 硬门控 |
| 澄清 | 无界、随意 | 有界(3 轮 × 3-5 问) |
| 覆盖 | 靠自觉 | 9 类高影响强制覆盖 |
| 契约派生 | 语义转换(易漏) | 实体/字段/错误码 → OpenAPI 结构化映射 |
| 事实可信 | 无来源 | 每条带 provenance |

> **这正是 SDD 的命门**:需求层不再是"自然语言散文",而是"可校验的结构化规范",后半段的契约/生成/门控才能接得住。
