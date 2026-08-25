---
name: build-domain-knowledge
description: 将已确认的需求澄清、PRD、OpenAPI 契约、线上复盘或评审结论沉淀为可追溯的跨项目领域知识，并在写入前完成检索、冲突检查、审批和覆盖验证。用户提到领域知识、业务规则、实体约定、状态流转、错误码、权限规则、沉淀约定、知识库缺口、更新业务知识、build domain knowledge 时必须使用；不要将未确认的 AI 推断直接写入 confirmed 知识库。
allowed-tools: Read, Bash, Write, Glob, Grep
---

# 构建领域知识

领域知识是 Harness 跨项目复用的业务资产，保存于 `config/domain-knowledge/{business,frontend,backend,qa}/`。它不同于仓库知识：

- **领域知识**回答“业务规则是什么、在什么范围生效、依据是什么”。
- **仓库知识**回答“当前项目如何组织、代码在哪里、工程约定是什么”。

只沉淀已经确认的规则。代码现状、AI 推测和未回答的问题只能作为候选或 `assumption`，不能伪装成事实。

## 适用输入与可信度

按来源决定可写入状态：

| 输入来源 | 可写入状态 | 处理方式 |
|---|---|---|
| 用户明确确认、审批 PRD、已确认契约、正式复盘结论 | `confirmed` | 可在用户确认候选内容后落库 |
| 代码现状、历史实现、评审建议 | `assumption` | 记录来源，要求业务确认后再升级 |
| Agent 推断 | `assumption` | 不得直接写入 `confirmed` |
| 相互矛盾或范围不明的信息 | 不写入 | 输出待澄清问题 |

## 知识条目格式

每条知识是带 JSON frontmatter 的 Markdown。元数据决定其可否参与精确覆盖判断：

- 必填：`id`、`domain`、`entity`、`type`、`status`、`source`。
- `id` 使用小写 slug，例如 `order-lifecycle`。
- `type` 可选：`rule`、`field`、`lifecycle`、`error-code`、`permission`、`ui-contract`、`qa-case`、`convention`。
- `status` 可选：`confirmed`、`assumption`、`deprecated`。
- 需要精确覆盖字段、状态、错误码时，分别填写 `fields`、`states`、`error_codes`。

不要手工拼 frontmatter；优先使用下方 `write` 命令生成与校验。

## 工作流

### 1. 明确范围和输入来源

先确认：业务域（business/frontend/backend/qa）、实体、规则类型、适用范围、来源和确认状态。

- 用户未给出确认来源时，先提出候选知识，不落库。
- 已存在知识时先检索，避免创建同义重复或覆盖旧规则：

```bash
python3 lib/domain_knowledge.py search "<实体或规则关键词>" --domain <business|frontend|backend|qa>
```

### 2. 提取候选规则并做冲突检查

将输入拆分成最小可复用约定：字段语义、状态流转、权限、错误码、幂等、前端展示契约或 QA 验收规则。

每条候选必须明确：

1. **实体与范围**：规则适用于谁、哪些流程；
2. **规则正文**：可执行的约定，避免“适当处理”等歧义；
3. **结构化事实**：相关字段、枚举状态、错误码；
4. **来源与状态**：为什么可信、是否已确认；
5. **冲突处理**：与现有规则不一致时，列出差异，要求用户决定保留、合并、替换或废弃。

### 3. 展示候选并请求确认

首次写入或有冲突时，先用以下格式向用户展示，等待确认：

```markdown
## 领域知识候选
- 域 / 实体：business / Order
- 类型：lifecycle
- 状态：confirmed
- 来源：user_document
- 结构化定义：fields=[...]；states=[...]；error_codes=[...]
- 规则：...
- 影响：Stage 1/2/5A/5B/8 将可按需检索该规则
- 冲突：无 / 与 <entry-id> 的 <字段或错误码> 定义冲突
```

只有用户确认候选、或输入本身是已审批的正式结论且用户明确要求沉淀时，才能写入 `confirmed`。

### 4. 安全落库

使用 `write`，默认 `create` 不覆盖已有条目：

```bash
python3 lib/domain_knowledge.py write business order-lifecycle \
  "同 Idempotency-Key 重复提交返回原订单，不重复创建。" \
  --entity Order --type lifecycle --status confirmed --source user_document \
  --fields '[{"name":"orderId","type":"string","required":true}]' \
  --states '["PENDING","PAID","CANCELLED"]' \
  --error-codes '[{"code":409,"meaning":"重复订单"}]'
```

写入模式：

- `create`：默认，仅新条目；同名即拒绝。
- `merge`：仅同实体，合并不重复的结构化定义与正文。
- `replace`：替代已有规则或经人工核对后覆盖冲突；必须在回复中说明替换原因与影响。

验证条目：

```bash
python3 lib/domain_knowledge.py validate config/domain-knowledge/business/order-lifecycle.md
```

### 5. 验证对需求 Spec 的覆盖

对结构化需求 Spec 运行覆盖报告：

```bash
python3 lib/domain_knowledge.py gaps <spec.json> --domain business
```

阅读结构化结果，重点处理：

- `missing_entity`：实体没有已确认知识；
- `missing_field_definition`：字段名称存在不代表语义已定义；
- `missing_state_definition`：状态流转或展示规则不完整；
- `missing_error_mapping`：错误码没有业务含义；
- `conflicting_knowledge`：已确认规则互相矛盾；
- `legacy_entries`：旧版无元数据文件仅供检索，不作为精确覆盖依据。

缺口应回流到需求澄清或形成候选条目；不得为了消除 gap 编造 confirmed 规则。

## 与 Harness 阶段的关系

- Stage 1：用 business / qa 知识发现需求、字段、验收缺口。
- Stage 2：用 business / backend / frontend 知识补全契约字段、状态和错误语义。
- Stage 5A：检索 business / backend 的幂等、权限、错误码约定。
- Stage 5B：检索 business / frontend 的状态展示和交互契约。
- Stage 8：检索 business / qa 的边界、错误码与验收规则。

按实体或关键词检索相关条目，不要把整个知识库无差别注入上下文。

## 完成输出

完成后汇报：写入或变更的条目、来源与状态、检测到的冲突、Spec 覆盖变化、仍需业务确认的问题。若没有确认来源，输出候选和问题，不写文件。
