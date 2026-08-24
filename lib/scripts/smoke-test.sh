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
echo "==> transition 闭环自测..."
python3 tests/test_transition.py
echo "==> hooks 协议自测..."
python3 tests/test_hooks_protocol.py
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
echo "==> requirements_spec 自测..."
python3 tests/test_requirements_spec.py
echo "==> domain_knowledge 自测..."
python3 tests/test_domain_knowledge.py
echo "==> feasibility 自测..."
python3 tests/test_feasibility.py
echo "==> repo_knowledge 自测..."
python3 tests/test_repo_knowledge.py
echo "==> code_graph 自测..."
python3 tests/test_code_graph.py
echo "==> coverage_collector 自测..."
python3 tests/test_coverage_collector.py
echo "==> code_review 自测..."
python3 tests/test_code_review.py
echo "==> experience 自测..."
python3 tests/test_experience.py
echo "==> parallel_wave_scheduler 自测..."
python3 tests/test_parallel_wave_scheduler.py
echo "==> context_orchestrator 自测..."
python3 tests/test_context_orchestrator.py
echo "==> smart_retry 自测..."
python3 tests/test_smart_retry.py
echo "==> self_heal 自测..."
python3 tests/test_self_heal.py
echo "==> notifier 自测..."
python3 tests/test_notifier.py
echo "==> Smoke test OK"
