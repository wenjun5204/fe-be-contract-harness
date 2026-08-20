#!/usr/bin/env bash
# 冒烟测试入口。
# M0 阶段:manifest 校验 + workflow_fsm 自测;后续阶段接入契约一致性 / 四栈适配冒烟。
set -euo pipefail

cd "$(dirname "$0")/../.."

echo "==> Smoke test (M0)..."
bash lib/validate-manifest.sh
echo "==> workflow_fsm 自测..."
python3 tests/test_workflow_fsm.py
echo "==> Smoke test OK"
