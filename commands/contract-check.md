---
name: contract-check
version: "0.1.0"
platforms: ["catpaw", "catclaw", "claude-code", "codex", "openclaw", "opencode"]
skills: ["fe-be-contract-workflow"]
description: 跨栈一致性校验(后端/前端对契约的覆盖是否一致)
argument-hint: <contract>
allowed-tools: Read, Bash
---

@skills/fe-be-contract-workflow/SKILL.md

## Task

跨栈一致性校验(后端/前端三方一致):

```bash
python3 lib/contract/cli.py check <contract>
```

任一栈的 routes/models 未完整覆盖契约 → 阻断。
