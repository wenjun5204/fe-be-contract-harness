#!/usr/bin/env bash
# 冒烟测试入口。
# M0/M1:manifest 校验 + FSM/state/parser/codegen 自测。
set -euo pipefail

cd "$(dirname "$0")/../.."

echo "==> Smoke test (M0)..."
bash lib/validate-manifest.sh
echo "==> workflow_fsm 自测..."
python3 tests/test_workflow_fsm.py
echo "==> state_manager 自测..."
python3 tests/test_state_manager.py
echo "==> parser 自测..."
python3 tests/test_parser.py
echo "==> codegen 自测..."
python3 tests/test_codegen.py
echo "==> consistency 自测..."
python3 tests/test_consistency.py
echo "==> Smoke test OK"
