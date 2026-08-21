---
name: build-domain-knowledge
description: 构建/更新领域知识(业务/前端/后端/QA 四方向)。从需求澄清结论沉淀业务规则/实体约定/错误码,写入领域知识库,支撑需求分析识别模糊点。触发词:领域知识、业务知识、沉淀约定、build domain knowledge。当需求澄清产生结论、或需要沉淀业务规则时使用。
allowed-tools: Read, Bash, Write
---

# 构建领域知识(build-domain-knowledge)

把「澄清结论」沉淀成「可复用的领域知识」,支撑 requirements-analyst 的模糊点识别(`identify_gaps`)。

## 工作流

1. **提取结论**:从需求澄清 / 评审中提取实体约定、业务规则、错误码
2. **选择方向**:business(业务)/ frontend / backend / qa
3. **沉淀知识**:`python3 lib/domain_knowledge.py seed <方向> <名称> <内容>`
4. **验证覆盖**:`python3 lib/domain_knowledge.py gaps <spec.json>` 确认模糊点减少

## 产出

- `config/domain-knowledge/<方向>/<名称>.md`

## 约束

- 只沉淀「已确认」的结论;未确认的记为假设(assumption),不写入知识库
- 知识条目简洁,是「约定」而非「教程」
- 与 repo-knowledge 分工:领域知识 = 「业务约定」;仓库知识 = 「仓库结构」
