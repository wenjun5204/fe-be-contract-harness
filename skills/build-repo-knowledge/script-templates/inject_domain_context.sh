#!/usr/bin/env bash
# 注入领域上下文(AGENTS.md + domain-model.md)
# 用于 Stage 1(需求分析)/Stage 8(测试用例)的 before 注入
# 只注入业务术语和领域模型,不注入全量服务文档,避免稀释重点
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENTS_DOCS="$REPO_ROOT/.agents/docs"

echo "=== {{PROJECT_NAME}} 领域上下文 ==="
echo ""

[ -f "$REPO_ROOT/AGENTS.md" ] && { echo "--- 模块全景 & 枚举速查 ---"; cat "$REPO_ROOT/AGENTS.md"; echo ""; }
[ -f "$AGENTS_DOCS/domain-model.md" ] && { echo "--- 领域模型 ---"; cat "$AGENTS_DOCS/domain-model.md"; echo ""; }

echo "=== 领域上下文注入完毕 ==="
