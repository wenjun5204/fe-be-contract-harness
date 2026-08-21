#!/usr/bin/env bash
# 冒烟测试入口。
# M0/M1:manifest 校验 + FSM/state/parser/codegen 自测。
set -euo pipefail

cd "$(dirname "$0")/../.."

echo "==> Smoke test..."
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
echo "==> delegation 自测..."
python3 tests/test_delegation.py
echo "==> checkpoint 自测..."
python3 tests/test_checkpoint.py
echo "==> coverage_gate 自测..."
python3 tests/test_coverage_gate.py
echo "==> agent 完整性校验..."
python3 lib/validate-agents.py
echo "==> stack_adapter 自测..."
python3 tests/test_stack_adapter.py
echo "==> runner 自测..."
python3 tests/test_runner.py
echo "==> planner 自测..."
python3 tests/test_planner.py
echo "==> eval 评测..."
python3 evals/run_evals.py | tail -1
echo "==> Smoke test OK"
