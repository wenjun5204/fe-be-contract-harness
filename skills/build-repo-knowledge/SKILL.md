---
name: build-repo-knowledge
description: 为本地 Git 项目构建、校验和增量维护 AI Agent 仓库知识库。安全创建目标项目的 AGENTS.md、.agents/docs 架构/规范/领域/服务文档骨架，并生成带按需选择和上下文预算的注入脚本。用户提到构建知识库、理解项目、分析仓库、项目冷启动、build repo knowledge、仓库知识、生成 AGENTS.md，或仓库结构变化需要更新 Agent 上下文时使用。
allowed-tools: Read, Bash, Glob, Grep, Write
---

# 构建仓库知识库

仓库知识描述“当前项目长什么样”：技术栈、模块、代码约定、实际领域模型和服务调用关系。它写入**目标项目**的 `AGENTS.md` 与 `.agents/`，应和项目代码一起维护。

本 Skill 不会把代码推断直接包装成业务事实：每个 LLM 生成结论都必须保留代码证据路径，并标注为事实、推断或待确认。

## 输出与完成标准

```text
{项目路径}/
├── AGENTS.md
└── .agents/
    ├── docs/
    │   ├── architecture.md
    │   ├── conventions.md
    │   ├── domain-model.md
    │   └── services/service-*.md
    ├── plans/
    ├── test-examples/{baseline,delivery}/
    └── scripts/
        ├── inject_context.sh
        ├── inject_conventions_context.sh
        ├── inject_domain_context.sh
        └── inject_test_examples.sh
```

仅创建骨架不等于知识库完成。以下核心文件必须存在且不包含 `待 build-repo-knowledge 生成` 占位符：

- `AGENTS.md`
- `.agents/docs/architecture.md`
- `.agents/docs/conventions.md`
- `.agents/docs/domain-model.md`

## Step 1：先校验目标仓库

```bash
python3 lib/repo_knowledge.py validate-repo <repo>
```

要求目标是可读、可写的 Git 仓库。命令同时返回依赖文件、Harness 深度支持的技术栈（React/Vue/Node/Java）和警告。

- 未发现依赖文件：可以降级扫描目录，但必须在产物中保留低置信度说明。
- Go/Python 的依赖文件会被识别为仓库信号，但当前没有对应的深度 adapter；不要虚构其路由、服务或测试约定。
- 校验失败时停止，不创建任何文件。

## Step 2：安全初始化与确定性扫描

先确认写入模式，再执行：

```bash
python3 lib/repo_knowledge.py scaffold <repo> --name <项目名> --mode create
python3 lib/repo_knowledge.py build <repo>
```

写入模式：

| 模式 | 行为 |
|---|---|
| `create` | 默认；已有文件跳过，绝不覆盖 |
| `merge` | 仅补缺失文件，保留已有内容 |
| `replace` | 覆盖现有骨架或脚本；仅用户明确确认后使用 |

命令会返回 `created`、`skipped`、`replaced`。如果用户已有修改过的注入脚本，默认必须保留，先展示差异再请求 replace 确认。

确定性扫描仅提供技术栈、目录、关键文件和推荐构建/测试命令；它是后续分析的证据起点，不是完整架构结论。

## Step 3：生成可验证的核心文档

在写入前阅读相关代码。每一份文档都应以“代码证据 → 结论”的方式组织，避免空泛描述。

| 文档 | 至少包含 | 证据要求 |
|---|---|---|
| `architecture.md` | 入口、模块边界、分层、主要调用链、外部集成 | 路径 + 模块/符号名 |
| `conventions.md` | 命名、异常处理、数据访问、测试、禁止事项 | 至少一个真实代码示例路径 |
| `domain-model.md` | 实体、枚举、状态、边界上下文 | 区分代码事实与业务待确认项 |
| `services/service-*.md` | 责任、关键方法、依赖、输入输出、调用方 | 服务文件与关联符号 |
| `AGENTS.md` | 仓库概览、模块导航、常用命令、关键约定、文档链接 | 链接到上述文档 |

对无法从代码确定的业务含义，写为“待确认”，不要伪造确定结论；需要跨项目复用的已确认业务规则应交给 `build-domain-knowledge`。

## Step 4：完成前校验

```bash
python3 lib/repo_knowledge.py validate-knowledge <repo>
```

未通过时，不得报告“知识库已完成”。根据结果补齐：

- `missing`：文件缺失；
- `placeholders`：骨架仍未填充；
- `services`：已发现的服务文档，用于补充 AGENTS 索引和按需注入。

## Step 5：按需注入，不全量塞上下文

注入脚本均有字符预算，避免大仓库把所有服务文档塞入 prompt：

```bash
# 技术方案/实现：仅加载核心文档；服务文档必须显式选择
.agents/scripts/inject_context.sh --service order-service --max-chars 12000

# 代码评审
.agents/scripts/inject_conventions_context.sh --max-chars 8000

# 需求分析/测试用例
.agents/scripts/inject_domain_context.sh --max-chars 8000
.agents/scripts/inject_test_examples.sh --baseline --max-chars 8000
```

阶段建议：

| 阶段 | 优先上下文 |
|---|---|
| Stage 1 | `inject_domain_context.sh` |
| Stage 3 | `inject_context.sh`，按当前模块指定 `--service` |
| Stage 5A/5B | `inject_context.sh`，按改动服务指定 `--service` |
| Stage 7 | `inject_conventions_context.sh` |
| Stage 8 | `inject_domain_context.sh` + `inject_test_examples.sh` |

生产编排优先交给 `context_orchestrator` 选 section 和裁剪；脚本用于本地调用或平台接入适配。

## 完成汇报

汇报必须包含：扫描到的技术栈与置信度、创建/跳过/替换的文件、核心文档校验结果、关键代码证据、尚未确认的推断，以及推荐的注入命令。若存在占位符或缺失文件，明确报告未完成项。

## 与领域知识的分工

- `build-repo-knowledge`：当前项目的结构、代码约定、实现事实，写入目标项目 `.agents/`。
- `build-domain-knowledge`：跨项目复用的已确认实体、规则、状态、错误码，写入 Harness 的 `config/domain-knowledge/`。
