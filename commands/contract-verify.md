---
name: contract-verify
version: "0.1.0"
platforms: ["catpaw", "catclaw", "claude-code", "codex", "openclaw", "opencode"]
skills: ["fe-be-contract-workflow"]
description: 校验生成产物的幂等性与结构忠实性(G1 生成门)
argument-hint: <contract> --stack <stack>
allowed-tools: Read, Bash
---

@skills/fe-be-contract-workflow/SKILL.md

## Task

G1 生成门校验(幂等 + 结构忠实):

```bash
python3 lib/contract/cli.py verify <contract> --stack <stack>
```

失败 → 生成器有漂移或契约有缺失,阻断进入编码。
