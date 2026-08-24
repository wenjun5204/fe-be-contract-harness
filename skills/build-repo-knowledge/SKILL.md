---
name: build-repo-knowledge
description: 为本地 Git 项目自动构建 AI Agent 知识库。分析仓库结构、技术栈、模块依赖,生成 AGENTS.md 索引和 .agents/ 目录下的架构设计、编码规范、领域模型、服务文档,并生成 4 个按阶段注入上下文的脚本。触发词:构建知识库、理解项目、分析仓库、项目冷启动、build repo knowledge、仓库知识、生成 AGENTS.md。当首次进入新仓库、仓库结构变化、或需要理解项目技术栈与约定时使用。
allowed-tools: Read, Bash, Glob, Grep, Write
---

# 为代码仓库自动构建 AI Agent 知识库

分析项目架构、编码规范、领域模型,生成可复用的知识库文档,并按阶段自动注入到 fe-be-contract-harness 的 12 阶段工作流。

## 前置要求

- ✅ 提供的项目路径是有效本地目录,且是 Git 仓库(含 `.git/`)
- ✅ 项目中至少有一个依赖文件(pom.xml / package.json / go.mod / requirements.txt 等)
- ✅ Agent 有权限读取该项目目录

## 输出位置(写入用户项目路径)

```
{项目路径}/
├── AGENTS.md                              ← 索引文档
└── .agents/
    ├── docs/
    │   ├── architecture.md                ← 架构设计(分层/核心类/调用链/外部集成)
    │   ├── conventions.md                 ← 编码规范(命名/异常/数据库/测试)
    │   ├── domain-model.md                ← 领域模型(实体/状态机/边界上下文)
    │   └── services/service-*.md          ← 每核心服务文档
    ├── test-examples/{baseline,delivery}/ ← 测试用例库(可选参考)
    ├── plans/                             ← 需求计划(后续)
    └── scripts/
        ├── inject_context.sh              ← 全量注入
        ├── inject_conventions_context.sh  ← 规范注入
        ├── inject_domain_context.sh       ← 领域注入
        └── inject_test_examples.sh        ← 测试注入
```

## 执行步骤

### Step 1:确定性骨架(调 lib/repo_knowledge.py)

```bash
python3 lib/repo_knowledge.py scaffold <repo> --name <项目名>
```

自动创建 `.agents/` 目录骨架 + 复制 4 个注入脚本(替换 `{{PROJECT_NAME}}`)。同时:

```bash
python3 lib/repo_knowledge.py build <repo>   # 技术栈/目录结构/关键文件/命令(确定性)
```

### Step 2:生成 4 类核心文档(LLM 分析代码)

分析代码,填充 `.agents/docs/` 下 4 类文档:

| 文档 | 内容 |
|------|------|
| `architecture.md` | 系统架构、分层、核心类列表、模块调用链、外部系统集成 |
| `conventions.md` | 设计模式、命名规范、异常处理、数据库操作、测试规范(附代码示例) |
| `domain-model.md` | 核心实体关系、业务概念、状态机、边界上下文 |
| `services/*.md` | 每个核心服务:实体表、枚举、关键方法、调用链 |

### Step 3:生成 AGENTS.md 索引

包含:仓库概述、模块全景表、依赖拓扑、快速导航、关键约定与禁止事项、核心枚举速查。

### Step 4:按阶段注入映射(接入 12 阶段)

| 阶段 | 注入脚本 | 注入内容 |
|------|----------|----------|
| Stage 1 需求分析 | `inject_domain_context.sh` | 领域模型 + 业务概念 |
| Stage 3 技术方案 | `inject_context.sh` | 全量架构 + 规范 + 领域 |
| Stage 5A/5B 实现 | `inject_context.sh` | 全量上下文 |
| Stage 7 代码评审 | `inject_conventions_context.sh` | 规范 + 禁止事项 |
| Stage 8 测试用例 | `inject_domain_context.sh` + `inject_test_examples.sh` | 领域 + 测试用例库 |

> 各阶段 subagent 启动时执行对应注入脚本,把知识库上下文写入 prompt(脚本输出到 stdout,由框架注入)。

### Step 5:处理测试用例库(可选)

用户提供参考项目的 `.agents/test-examples` 时,复制到 `{项目}/.agents/test-examples/`(需含 baseline/ 或 delivery/)。未提供则脚本仍可用(输出基础规范)。

### Step 6:输出完成摘要

报告生成的文件清单 + 后续建议(提交到 git 共享、定期更新、各阶段自动注入)。

## 工作原理

1. **依赖文件检测** → 识别技术栈(pom.xml/package.json/go.mod/requirements.txt)
2. **目录结构扫描** → 识别单模块/多模块
3. **代码结构分析** → 按技术栈适配(Java→Controller/Service/DAO,Node→module/service,前端→组件/hook)
4. **文档生成** → 架构/规范/领域模型/服务文档
5. **注入脚本** → 按阶段注入不同上下文

## 异常处理

| 异常 | 处理 |
|------|------|
| 路径不存在 / 非 Git 仓库 | 提示,要求重新提供 |
| 无依赖文件 | 扫描目录结构生成基础知识库(准确度有限) |
| 已存在知识库 | 询问:覆盖 / 增量更新 |
| 权限不足 | 中止,提示检查权限 |

## 与 domain-knowledge 的分工

- **build-repo-knowledge**(本 skill)= 「这个仓库长什么样」:技术栈 / 结构 / 规范 / 领域模型 → 输出到**目标项目 `.agents/`**,团队共享
- **build-domain-knowledge** = 「这个业务有哪些约定」:实体 / 规则 / 错误码 → 输出到 **harness `config/domain-knowledge/`**,跨项目复用
