#!/usr/bin/env bash
# 注入测试用例库(按模块/全部)
# 用于 Stage 8(测试用例生成)的 before 注入
# 用法: inject_test_examples.sh [--all|--baseline|--delivery]
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLES="$REPO_ROOT/.agents/test-examples"
MODE="${1:---all}"

echo "=== {{PROJECT_NAME}} 测试用例库 ==="
echo ""

dump() {
  local dir="$1" label="$2"
  if [ -d "$dir" ]; then
    for f in "$dir"/*.md; do
      [ -f "$f" ] && { echo "--- $label: $(basename "$f" .md) ---"; cat "$f"; echo ""; }
    done
  fi
}

case "$MODE" in
  --baseline)  dump "$EXAMPLES/baseline" "基线用例" ;;
  --delivery)  dump "$EXAMPLES/delivery" "交付用例" ;;
  --all)       dump "$EXAMPLES/baseline" "基线用例"; dump "$EXAMPLES/delivery" "交付用例" ;;
esac

echo "=== 测试用例库注入完毕 ==="
