# fe-be-contract-harness

一个面向前后端协作的**契约驱动 SDLC Harness**。它以 OpenAPI 3.x 为前后端接口的唯一事实源（SSOT），把需求、契约、代码生成、质量校验、人工确认和交付串成一条可验证、可恢复的工作流。

> 当前最适合的使用方式：把它当作“确定性流程内核 + Agent 协作协议”。
> - 确定性部分可以本地直接运行、测试和校验；
> - LLM 阶段会生成带 receipt 和知识上下文的 dispatch directive；
> - 真正由 CatPaw / Claude Code / OpenClaw 等平台启动 Agent、回传结果的适配仍需按目标平台验证。

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [核心概念](#核心概念)
- [工作流总览](#工作流总览)
- [5 分钟体验](#5-分钟体验)
- [常用命令](#常用命令)
- [运行 Runner 与 Agent 委派](#运行-runner-与-agent-委派)
- [知识库与自动上下文](#知识库与自动上下文)
- [状态、门控与人工确认](#状态门控与人工确认)
- [契约能力与支持范围](#契约能力与支持范围)
- [测试与目录结构](#测试与目录结构)
- [当前边界](#当前边界)

---

## 它解决什么问题

传统前后端协作常见的问题包括：接口文档与实现漂移、前后端类型不一致、需求没有被结构化、AI Agent 绕过必要检查、多人或多 Agent 的结果无法审计。

Harness 的对应机制如下：

| 问题 | 机制 |
|---|---|
| 接口定义分散 | OpenAPI 契约作为 SSOT |
| 多栈重复定义类型 | 从同一契约生成 React / Vue / Node / Java 骨架 |
| 生成结果质量不稳定 | G1 生成门、跨栈一致性检查、漂移检测 |
| 需求不完整就进入开发 | 结构化 `requirements_spec` 与 Stage 1 硬门控 |
| Agent 声称完成但没有证据 | receipt 登记、一次性消费、产出与 evidence 门控 |
| 需要人工判断的节点被跳过 | checkpoint：approve / revise / skip |
| Agent 缺少项目和业务上下文 | 领域知识、仓库知识、按 Stage/实体/预算生成的 dispatch context |

---

## 核心概念

### 1. 契约（Contract）

OpenAPI 3.x 文件，例如 `examples/petstore.yaml`。它描述接口、模型、请求和响应，是代码生成、一致性检查与漂移检测的输入。

### 2. Stage（阶段）

工作流由 12 个阶段组成。阶段 ID 使用 `0` 到 `10`，其中 Stage 5 分为 `5A`（后端）和 `5B`（前端），因此总数是 12。

### 3. 状态文件（state.json）

每次运行都有一个状态文件，记录各阶段的状态、输出、receipt、checkpoint、evidence 和时间。它支持查看进度和断点续跑。

### 4. Receipt（委派凭据）

主 Agent 或 runner 签发子 Agent 任务时生成的凭据。阶段完成或跳过前必须先登记 receipt；终态后 receipt 被消费，不能重放。

### 5. Checkpoint（人工卡点）

对需求、契约、一致性、交付等高风险阶段设置人工确认。确认可以：

- `approve`：接受结果，进入 completed；
- `revise`：要求修订，回到 running；
- `skip`：仅在该 checkpoint 类型允许时跳过。

### 6. Dispatch context（派发上下文）

runner 为 LLM 阶段签发任务时，附带的 `dispatch-context/v1`。它会根据：

1. 当前 Stage；
2. OpenAPI 的 schema 实体；
3. 可选目标仓库的 `.agents/docs/`；
4. token 预算；

自动选择相关领域知识和仓库知识。上下文缺失不会阻断冷启动，而会写入 `warnings`。

---

## 工作流总览

```text
输入需求 / OpenAPI
        │
        ▼
0 初始化
        │
        ▼
1 需求分析 ──人工确认──► 2 契约设计 ──人工确认──► 3 仓库识别与技术方案
        │                                                   │
        │                                                   ▼
        └──────────────────────────────────────────────► 4 分支管理
                                                            │
                                           ┌────────────────┴────────────────┐
                                           ▼                                 ▼
                                      5A 后端实现                        5B 前端实现
                                           └────────────────┬────────────────┘
                                                            ▼
                                               6 前后端一致性校验
                                                      ──人工确认──►
                                           ┌────────────────┴────────────────┐
                                           ▼                                 ▼
                                      7 提交与 PR                       8 测试用例生成
                                           └────────────────┬────────────────┘
                                                            ▼
                                                    9 提测与部署
                                                            ▼
                                                   10 交付报告
```

### 阶段说明

| Stage | 名称 | 主要产出 | checkpoint |
|---|---|---|---|
| 0 | 初始化 | `execution_plan` | 无 |
| 1 | 需求分析 | 需求文档、结构化 Spec、质量门结果 | `mandatory_review` |
| 2 | 接口契约设计 | `openapi_contract` | `mandatory_review` |
| 3 | 仓库识别与技术方案 | 仓库确认、设计文档 | `mandatory_review` |
| 4 | 分支管理 | `branch_name` | 无 |
| 5A | 后端实现 | 变更文件、覆盖率 | 无 |
| 5B | 前端实现 | 变更文件、覆盖率 | 无 |
| 6 | 前后端一致性校验 | 一致性报告 | `mandatory_review` |
| 7 | 提交与 PR | `pr_url` | `artifact_review` |
| 8 | 测试用例生成 | `test_cases` | `artifact_review` |
| 9 | 提测与部署 | `deploy_result` | `artifact_review` |
| 10 | 交付报告 | `delivery_report` | `artifact_review` |

### 当前 runner 的执行方式

| 类型 | 阶段 | 当前行为 |
|---|---|---|
| 确定性执行 | 0、5A、5B、6、10 | 本地执行或生成，并通过 `transition` 进入终态 |
| LLM 委派 | 1、2、3、4、7、8、9 | 非 `--auto` 时只生成 dispatch directive，不会伪造完成 |
| 演示自动模式 | `--auto` | 对 LLM 阶段记录带批准的 skip；自动批准 checkpoint，用于本地完整演示 |

---

## 5 分钟体验

### 前置依赖

- Python 3.8+；
- `pyyaml`（解析 YAML OpenAPI）；
- Node.js 18+（用于 `npm` 脚本；生成核心本身主要依赖 Python）。

### 1. 运行完整演示

```bash
npm run demo
```

演示会在临时目录完成：四栈生成、G1 校验、跨栈一致性、状态迁移门控、覆盖率门控和 delegation hook 校验。不会在仓库中留下生成产物。

### 2. 生成一个栈的代码

```bash
python3 lib/contract/cli.py generate examples/petstore.yaml \
  --stack node \
  --out gen/node
```

可用栈：

```bash
python3 lib/contract/cli.py stacks
```

当前包含 React、Vue、Node、Java。

### 3. 运行契约校验

```bash
# G1：生成器是否可稳定从契约生成该技术栈产物
python3 lib/contract/cli.py verify examples/petstore.yaml --stack node

# 四栈模型是否一致
python3 lib/contract/cli.py check examples/petstore.yaml

# 已生成产物是否与最新契约漂移
python3 lib/contract/cli.py drift examples/petstore.yaml \
  --stack node \
  --gen-dir gen/node
```

### 4. 运行编排器

```bash
# 非自动模式：生成 LLM 阶段 directive，并真实执行确定性阶段可推进的部分
python3 lib/runner.py run examples/petstore.yaml \
  --out gen \
  --state state.json \
  --stacks node,react

# 自动演示模式：显式跳过 LLM 阶段，走完整状态机闭环
python3 lib/runner.py run examples/petstore.yaml \
  --out gen \
  --state state.json \
  --stacks node,react \
  --auto

# 查看状态
python3 lib/runner.py status --state state.json
```

> 建议将 `state.json` 和 `gen/` 作为运行产物处理，不要提交到业务代码仓库。

---

## 常用命令

### 契约命令

```bash
# 列出技术栈
python3 lib/contract/cli.py stacks

# 生成
python3 lib/contract/cli.py generate <openapi.yaml> --stack <react|vue|node|java> --out <目录>

# G1 生成门
python3 lib/contract/cli.py verify <openapi.yaml> --stack <技术栈>

# 跨栈一致性
python3 lib/contract/cli.py check <openapi.yaml>

# 漂移检测
python3 lib/contract/cli.py drift <openapi.yaml> --stack <技术栈> --gen-dir <生成目录>
```

### Runner 命令

```bash
python3 lib/runner.py run <openapi.yaml> \
  --out <生成目录> \
  --state <状态文件> \
  --stacks react,vue,node,java \
  --repo <可选目标业务仓库> \
  --context-max-tokens 4000

python3 lib/runner.py status --state <状态文件>
```

参数说明：

| 参数 | 含义 |
|---|---|
| `--out` | 各栈生成产物根目录，默认 `gen` |
| `--state` | 工作流状态文件，默认 `state.json` |
| `--stacks` | 需要处理的技术栈，逗号分隔 |
| `--auto` | 演示自动模式，不是正式人工审批替代品 |
| `--repo` | 目标业务仓库；用于读取 `.agents/docs/` 仓库知识 |
| `--context-max-tokens` | 每个 LLM directive 的知识上下文预算，默认 4000 |

---

## 运行 Runner 与 Agent 委派

### 非自动模式会输出什么

非 `--auto` 运行时，LLM 阶段的 `events` 会包含 `kind: "agent"`。`detail` 是一份 dispatch directive，结构类似：

```json
{
  "stage": "2",
  "subagent": "contract/contract-designer",
  "receipt": {
    "schema": "stage-subagent/v1",
    "stage": "2",
    "subagent": "contract/contract-designer",
    "token": "runner",
    "action": "execute"
  },
  "contract": "examples/petstore.yaml",
  "context": {
    "schema": "dispatch-context/v1",
    "entities": ["Pet"],
    "max_tokens": 4000,
    "sections": [
      {"name": "agenda", "text": "...", "estimated_tokens": 20}
    ],
    "warnings": []
  }
}
```

真实平台适配器应：

1. 选择 `subagent` 对应 Agent；
2. 将 `context.text` 和 `contract` 注入 Agent 上下文；
3. 保留 receipt 并在 Agent 回传时使用；
4. 让 Agent 提交 `outputs`、`evidence`；
5. 通过 `lib/transition.py` 推进阶段，而不是直接改状态文件。

### 手工推进一个阶段

这是理解门控机制的最小示例。实际平台应自动完成这些动作。

```bash
# 先初始化状态文件
python3 lib/state_manager.py init state.json demo

# 1. 用 directive 中的 receipt 登记，防伪造
python3 lib/transition.py register state.json --receipt '<receipt JSON>'

# 2. 开始阶段（会检查前置）
python3 lib/transition.py start state.json 0

# 3. 提交产物、证据和 receipt
python3 lib/transition.py complete state.json 0 \
  --receipt '<receipt JSON>' \
  --outputs '{"execution_plan":"demo"}' \
  --evidence '[{"type":"plan","detail":"demo"}]'

# 查看汇总
python3 lib/state_manager.py summary state.json
```

如果当前 Stage 带 checkpoint，`complete` 且未提供 `--checkpoint` 时会进入 `checkpoint_pending`。随后可带相同 receipt 执行：

```bash
python3 lib/transition.py complete state.json <stage> \
  --receipt '<receipt JSON>' \
  --outputs '<outputs JSON>' \
  --checkpoint approve
```

常用恢复命令：

```bash
python3 lib/transition.py fail state.json 5A --reason "生成失败"
python3 lib/transition.py retry state.json 5A
```

---

## 知识库与自动上下文

Harness 有两类知识，**不要混用**。

### 领域知识：跨项目复用的已确认业务规则

位置：`config/domain-knowledge/`。

适合记录实体字段语义、状态流转、错误码、权限、前端展示契约和 QA 验收规则。条目有 `confirmed`、`assumption`、`deprecated` 状态；AI 推断不能直接写入 `confirmed`。

```bash
# 按关键词检索
python3 lib/domain_knowledge.py search "订单" --domain business

# 检查一条知识的 Schema
python3 lib/domain_knowledge.py validate config/domain-knowledge/business/order.md

# 根据结构化需求 Spec 查看实体/字段/状态/错误码覆盖缺口
python3 lib/domain_knowledge.py gaps <spec.json> --domain business
```

领域知识会按 OpenAPI schema 实体过滤后进入 dispatch context；`convention` 类型的跨实体约定会始终进入相关 Stage。

### 仓库知识：目标项目的实现事实

位置：目标业务仓库的 `AGENTS.md` 和 `.agents/`。

```bash
# 校验目标仓库是否可构建知识库
python3 lib/repo_knowledge.py validate-repo <repo>

# 安全创建骨架；默认不覆盖已有文件
python3 lib/repo_knowledge.py scaffold <repo> --name <项目名> --mode create

# 确定性扫描技术栈、目录、关键文件与建议命令
python3 lib/repo_knowledge.py build <repo>

# 验证核心文档已填充，不再只是占位符
python3 lib/repo_knowledge.py validate-knowledge <repo>
```

仓库知识的关键文件：

```text
<repo>/
├── AGENTS.md
└── .agents/
    ├── docs/
    │   ├── architecture.md
    │   ├── conventions.md
    │   ├── domain-model.md
    │   └── services/
    └── test-examples/
```

### 自动上下文如何选择

在 runner 中提供 `--repo` 后，会按 Stage 选择所需上下文：

| Stage | 领域知识 | 仓库知识 |
|---|---|---|
| 1 需求分析 | business、qa | `domain-model.md` |
| 2 契约设计 | business、backend、frontend | domain-model、conventions |
| 3 技术方案 | business | architecture、conventions、domain-model |
| 5A 后端实现 | business、backend | architecture、conventions、domain-model |
| 5B 前端实现 | business、frontend | architecture、conventions、domain-model |
| 6 一致性 | business | architecture、domain-model |
| 7 评审 | business | conventions |
| 8 测试 | business、qa | domain-model、test-examples |

如果预算不足，低优先级 section 会被省略并写进 `omitted_sections`；规则不会被截断成半段。

---

## 状态、门控与人工确认

所有正式终态都必须经过 `lib/transition.py`。门控顺序如下：

1. **FSM 合法性**：例如 pending 才能 start，running 才能 complete；
2. **前置就绪**：前置阶段必须 completed 或 skipped；
3. **必需产出**：必须满足 DAG 的 `required_outputs`；
4. **委派 fail-closed**：receipt 的 schema、阶段、Agent、登记状态都必须正确；
5. **checkpoint**：需要人工确认时不可直接进入终态；
6. **审计落盘**：outputs、receipt、evidence、checkpoint、完成时间写入状态文件；
7. **receipt 消费**：终态后凭据不可再次使用。

> `lib/state_manager.py` 的低层状态写能力仅用于恢复/调试。正式业务流程不要直接修改 `state.json`。

---

## 契约能力与支持范围

### 当前支持

- YAML / JSON OpenAPI 3.x；
- components schemas、基础类型、object、array、enum、`$ref`；
- JSON request body 和首个 2xx JSON response；
- React、Vue、Node、Java 的骨架生成；
- G1 生成门、跨栈一致性、生成产物漂移检测。

### 当前限制

- `allOf`、`oneOf`、`anyOf` 尚未完整支持；
- OpenAPI parser 是面向当前生成器的子集，不是完整 OpenAPI 实现；
- 生成结果是契约骨架，不替代业务逻辑、真实 DB、鉴权、完整测试或生产部署。

---

## 测试与目录结构

### 测试

```bash
npm run validate   # 校验 manifest / JSON 描述文件
npm test           # 全量确定性冒烟测试
npm run check      # validate + test
npm run demo       # 端到端演示
```

`npm test` 会执行 FSM、状态管理、契约解析、四栈生成、委派、checkpoint、hooks、知识库、上下文编排、runner、评测集等自测。

### 目录结构

```text
fe-be-contract-harness/
├── agents/                  # orchestrator / contract / codegen / quality Agents
├── commands/                # 斜杠命令定义
├── config/                  # 委派策略、契约规范、覆盖率、领域知识等
├── evals/                   # 契约回归评测集
├── examples/                # 示例 OpenAPI 契约
├── hooks/                   # delegation / checkpoint / coverage 等守卫
├── lib/                     # 确定性内核
│   ├── contract/            # 解析、生成、验证、一致性、漂移
│   ├── stack/               # 四技术栈 adapter
│   ├── runner.py            # 工作流 runner
│   ├── transition.py        # 唯一正式状态迁移入口
│   ├── context_orchestrator.py
│   ├── domain_knowledge.py
│   └── repo_knowledge.py
├── skills/                  # 主工作流、领域知识、仓库知识 Skills
└── tests/                   # 确定性自测
```

---

## 当前边界

- ✅ 契约解析、四栈生成、G1、跨栈一致性、状态机、receipt、checkpoint、覆盖率门控等确定性能力可本地运行和测试；
- ✅ 领域知识与仓库知识可被校验，并可以自动进入 LLM dispatch context；
- ✅ 非自动 runner 不会把 LLM 阶段伪装成已完成；
- ⚠️ 真实平台的“启动 Agent → 回传 StageResult → 调用 transition”适配尚需在 CatPaw / Claude Code / OpenClaw 等目标运行时完成并验证；
- ⚠️ `workflow-dag.json` 定义了并行分支关系；通用 `parallel_wave_scheduler` 已可用，但 runner 当前仍以顺序循环调度确定性分支；
- ⚠️ `--auto` 仅用于本地演示和测试，不应替代真实人工审批与部署。
