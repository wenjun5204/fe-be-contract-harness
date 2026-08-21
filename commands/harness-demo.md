---
name: harness-demo
version: "0.1.0"
platforms: ["catpaw", "catclaw", "claude-code", "codex", "openclaw", "opencode"]
skills: ["fe-be-contract-workflow"]
description: 运行端到端演示(四栈生成→G1门→一致性→状态机→门控)
argument-hint: [contract, 默认 examples/petstore.yaml]
allowed-tools: Bash
---

@skills/fe-be-contract-workflow/SKILL.md

## Task

端到端演示一条契约走完整个确定性闭环:

```bash
bash lib/scripts/demo-end-to-end.sh <contract>
```

或 `npm run demo`
