#!/usr/bin/env bash
# 按类型注入测试用例，并限制输出长度。
# 用法: inject_test_examples.sh [--all|--baseline|--delivery] [--max-chars <n>]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLES="$REPO_ROOT/.agents/test-examples"
MODE="--all"
MAX_CHARS=8000
while [ "$#" -gt 0 ]; do
  case "$1" in
    --all|--baseline|--delivery) MODE="$1"; shift ;;
    --max-chars) MAX_CHARS="${2:?--max-chars 需要整数}"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done
used=0
dump() {
  local dir="$1" label="$2" file remaining content
  [ -d "$dir" ] || return 0
  for file in "$dir"/*.md; do
    [ -f "$file" ] || continue
    remaining=$((MAX_CHARS - used)); [ "$remaining" -gt 0 ] || break
    content="$(head -c "$remaining" "$file")"
    printf '%s\n%s\n\n' "--- $label: $(basename "$file" .md) ---" "$content"
    used=$((used + ${#content}))
  done
}
echo "=== {{PROJECT_NAME}} 测试用例库 ==="
case "$MODE" in
  --baseline) dump "$EXAMPLES/baseline" "基线用例" ;;
  --delivery) dump "$EXAMPLES/delivery" "交付用例" ;;
  --all) dump "$EXAMPLES/baseline" "基线用例"; dump "$EXAMPLES/delivery" "交付用例" ;;
esac
echo "=== 测试用例库注入完毕（$used/$MAX_CHARS chars） ==="
