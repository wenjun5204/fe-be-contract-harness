#!/usr/bin/env bash
# 校验 harness 元文件的 JSON 语法与最小结构(health_check 入口)。
# M0 阶段:仅做 JSON 语法校验;后续阶段补齐引用完整性、平台字段、agent 注册校验。
set -euo pipefail

cd "$(dirname "$0")/.."

FILES=(
  "harness-manifest.json"
  "openclaw.plugin.json"
  "package.json"
  "lib/workflow-dag.json"
  "lib/state-schemas.json"
)

echo "==> Validating manifest JSON files..."
ok=0
for f in "${FILES[@]}"; do
  if python3 -c "import json,sys; json.load(open('$f'))" 2>/dev/null; then
    echo "  ok  $f"
  else
    echo "  ERR $f"
    ok=1
  fi
done

if [ "$ok" -ne 0 ]; then
  echo "==> Validation FAILED"
  exit 1
fi
echo "==> Validation OK"
