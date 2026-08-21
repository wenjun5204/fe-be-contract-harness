---
name: start-workflow
version: "0.1.0"
platforms: ["catpaw", "catclaw", "claude-code", "codex", "openclaw", "opencode"]
skills: ["fe-be-contract-workflow"]
description: 启动前后端契约驱动 SDLC 全流程(需求→契约→编码→一致性→评审→交付)
argument-hint: [需求描述 | openapi.yaml 路径] [--stack <react|vue|node|java>]
allowed-tools: Read, Write, Bash, Grep, Glob, TodoWrite
---

⚠️ 执行前必须先读技能:

@skills/fe-be-contract-workflow/SKILL.md

## Context

- 工作目录: !`pwd`
- Git 状态: !`git status -sb 2>/dev/null | head -5`
- 现有状态: !`python3 lib/state_manager.py summary state.json 2>/dev/null || echo "无状态,从 Stage 0 开始"`

## Task

按 SKILL.md 的 12 阶段工作流推进前后端契约驱动开发:

- 已提供 `openapi.yaml` → 从 Stage 3(仓库识别)开始,契约已存在
- 未提供契约 → 从 Stage 0 开始,先需求分析(Stage 1)再契约设计(Stage 2)
- 每个阶段派发给独立子 Agent(见 `config/delegation-policy.json`),契约是跨子 Agent 唯一接口
- 支持断点续跑:从 `state.json` 的 actionable 阶段继续
