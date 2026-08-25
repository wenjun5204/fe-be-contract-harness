#!/usr/bin/env bash
# 按需注入仓库上下文；默认只输出索引和三份核心文档，不再全量加载服务文档。
# 用法: inject_context.sh [--service <name>] [--max-chars <n>]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENTS_DOCS="$REPO_ROOT/.agents/docs"
SERVICE=""
MAX_CHARS=12000

while [ "$#" -gt 0 ]; do
  case "$1" in
    --service) SERVICE="${2:?--service 需要服务名}"; shift 2 ;;
    --max-chars) MAX_CHARS="${2:?--max-chars 需要整数}"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

used=0
emit_file() {
  local file="$1" label="$2"
  [ -f "$file" ] || return 0
  local remaining=$((MAX_CHARS - used))
  [ "$remaining" -gt 0 ] || return 0
  local content
  content="$(head -c "$remaining" "$file")"
  printf '%s\n%s\n\n' "--- $label ---" "$content"
  used=$((used + ${#content}))
}

echo "=== {{PROJECT_NAME}} 仓库上下文 ==="
emit_file "$REPO_ROOT/AGENTS.md" "AGENTS.md 索引"
emit_file "$AGENTS_DOCS/architecture.md" "架构设计"
emit_file "$AGENTS_DOCS/conventions.md" "编码规范"
emit_file "$AGENTS_DOCS/domain-model.md" "领域模型"
if [ -n "$SERVICE" ]; then
  emit_file "$AGENTS_DOCS/services/${SERVICE#service-}.md" "服务文档: $SERVICE"
fi
echo "=== 仓库上下文注入完毕（$used/$MAX_CHARS chars） ==="
