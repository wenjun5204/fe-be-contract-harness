#!/usr/bin/env bash
# 注入全量知识库上下文(AGENTS.md + architecture + conventions + domain-model + services)
# 用于 Stage 3(技术方案)/Stage 5A/5B(实现)的 before 注入
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENTS_DOCS="$REPO_ROOT/.agents/docs"

echo "=== {{PROJECT_NAME}} 仓库上下文 ==="
echo ""

[ -f "$REPO_ROOT/AGENTS.md" ] && { echo "--- AGENTS.md 索引 ---"; cat "$REPO_ROOT/AGENTS.md"; echo ""; }
[ -f "$AGENTS_DOCS/architecture.md" ] && { echo "--- 架构设计 ---"; cat "$AGENTS_DOCS/architecture.md"; echo ""; }
[ -f "$AGENTS_DOCS/conventions.md" ] && { echo "--- 编码规范 ---"; cat "$AGENTS_DOCS/conventions.md"; echo ""; }
[ -f "$AGENTS_DOCS/domain-model.md" ] && { echo "--- 领域模型 ---"; cat "$AGENTS_DOCS/domain-model.md"; echo ""; }

if [ -d "$AGENTS_DOCS/services" ]; then
  for f in "$AGENTS_DOCS/services/"*.md; do
    [ -f "$f" ] && { echo "--- 服务文档: $(basename "$f" .md) ---"; cat "$f"; echo ""; }
  done
fi

echo "=== 仓库上下文注入完毕 ==="
