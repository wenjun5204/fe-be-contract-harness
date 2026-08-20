#!/usr/bin/env bash
# 冒烟测试入口。
# M0 阶段:仅校验 manifest 可解析;后续阶段接入 FSM / 契约一致性 / 四栈适配的冒烟用例。
set -euo pipefail

cd "$(dirname "$0")/../.."

echo "==> Smoke test (M0)..."
bash lib/validate-manifest.sh
echo "==> Smoke test OK (仅 manifest 校验,更多用例待后续里程碑)"
