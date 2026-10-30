---
name: contract-generate
version: "0.1.0"
platforms: ["catpaw", "catclaw", "claude-code", "codex", "openclaw", "opencode"]
skills: ["fe-be-contract-workflow"]
description: 从 OpenAPI 契约生成指定技术栈的代码骨架
argument-hint: <contract> --stack <react|vue|react_native|expo|node|java> --out <dir>
allowed-tools: Read, Write, Bash
---

@skills/fe-be-contract-workflow/SKILL.md

## Task

从契约生成代码骨架,并跑 G1 生成门:

```bash
python3 lib/contract/cli.py generate <contract> --stack <stack> --out <dir>
python3 lib/contract/cli.py verify <contract> --stack <stack>   # G1:幂等 + 结构忠实
```

可用技术栈:`python3 lib/contract/cli.py stacks`(react / vue / react_native / expo / node / java)
