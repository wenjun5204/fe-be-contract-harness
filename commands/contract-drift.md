---
name: contract-drift
version: "0.1.0"
platforms: ["catpaw", "catclaw", "claude-code", "codex", "openclaw", "opencode"]
skills: ["fe-be-contract-workflow"]
description: 契约漂移检测(契约重生成 vs 磁盘已有产物)
argument-hint: <contract> --stack <stack> --gen-dir <dir>
allowed-tools: Read, Bash
---

@skills/fe-be-contract-workflow/SKILL.md

## Task

契约漂移检测(fail-closed):

```bash
python3 lib/contract/cli.py drift <contract> --stack <stack> --gen-dir <dir>
```

漂移 → 实现偏离契约或契约已变更未重新签字,阻断提交。
