#!/usr/bin/env bash
# 注入需求/测试阶段所需的索引与领域模型，并限制输出长度。
# 用法: inject_domain_context.sh [--max-chars <n>]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENTS_DOCS="$REPO_ROOT/.agents/docs"
MAX_CHARS=8000
[ "${1:-}" = "--max-chars" ] && { MAX_CHARS="${2:?--max-chars 需要整数}"; shift 2; }
[ "$#" -eq 0 ] || { echo "未知参数" >&2; exit 2; }
used=0
emit_file() {
  local file="$1" label="$2" remaining content
  [ -f "$file" ] || return 0
  remaining=$((MAX_CHARS - used)); [ "$remaining" -gt 0 ] || return 0
  content="$(head -c "$remaining" "$file")"
  printf '%s\n%s\n\n' "--- $label ---" "$content"
  used=$((used + ${#content}))
}
echo "=== {{PROJECT_NAME}} 领域上下文 ==="
emit_file "$REPO_ROOT/AGENTS.md" "模块全景与枚举速查"
emit_file "$AGENTS_DOCS/domain-model.md" "领域模型"
echo "=== 领域上下文注入完毕（$used/$MAX_CHARS chars） ==="
