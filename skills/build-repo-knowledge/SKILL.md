---
name: build-repo-knowledge
description: 构建/更新仓库知识(工程理解冷启动)。扫描仓库,提取技术栈/目录结构/关键文件/构建测试命令,沉淀为仓库知识。触发词:理解项目、分析仓库、项目冷启动、build repo knowledge、仓库知识。当首次进入新仓库、仓库结构变化、或需要理解项目技术栈与约定时使用。
allowed-tools: Read, Bash, Glob, Grep, Write
---

# 构建仓库知识(build-repo-knowledge)

把「看不懂的仓库」变成「可检索的仓库知识」,支撑 services-analyst(仓库识别)与 feasibility(可行性验证)。

## 工作流

1. **检测技术栈**:`python3 lib/repo_knowledge.py <repo>`(内部用 lib/stack 的 detect)
2. **扫描结构**:目录结构(前 2 层)、关键文件(package.json / pom.xml / nest-cli.json 等)
3. **提取约定**:构建 / 测试 / 覆盖率命令(从 lib/stack adapter),结合 `config/domain-knowledge/backend|frontend` 的约定
4. **沉淀知识**:写入 `config/repo-knowledge/<repo>.md`
5. **增量更新**:仓库变化时重新扫描,只更新变化部分

## 产出

- `config/repo-knowledge/<repo>.md`:技术栈 / 目录结构 / 关键文件 / 构建测试命令

## 约束

- 不扫描 node_modules / .git / 构建产物
- 知识是「索引」,不复制源码;细节按需读原文件
- 与 domain-knowledge 分工:仓库知识 = 「这个仓库长什么样」;领域知识 = 「这个业务有哪些约定」
