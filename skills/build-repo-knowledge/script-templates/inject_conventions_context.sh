#!/usr/bin/env bash
# 注入编码规范上下文(AGENTS.md + conventions.md)
# 用于 Stage 7(代码评审)的 before 注入
# 聚焦项目约定和禁止事项,帮助 Reviewer 识别违规代码
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENTS_DOCS="$REPO_ROOT/.agents/docs"

echo "=== {{PROJECT_NAME}} 编码规范上下文 ==="
echo ""

[ -f "$REPO_ROOT/AGENTS.md" ] && { echo "--- 关键约定 & 禁止事项 ---"; cat "$REPO_ROOT/AGENTS.md"; echo ""; }
[ -f "$AGENTS_DOCS/conventions.md" ] && { echo "--- 编码规范 ---"; cat "$AGENTS_DOCS/conventions.md"; echo ""; }

echo "=== 编码规范上下文注入完毕 ==="
