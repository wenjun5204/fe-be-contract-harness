#!/usr/bin/env bash
# 端到端演示:一条契约走完 生成 → G1 门 → 跨栈一致性 → 状态机推进 → 门控。
# 用法: bash lib/scripts/demo-end-to-end.sh [contract]
set -euo pipefail

cd "$(dirname "$0")/../.."

CONTRACT="${1:-examples/petstore.yaml}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "=== fe-be-contract-harness 端到端演示 ==="
echo "契约: $CONTRACT"
echo ""

echo "[1/6] 四栈代码生成"
for s in react vue node java; do
  python3 lib/contract/cli.py generate "$CONTRACT" --stack "$s" --out "$WORK/$s" >/dev/null
  n=$(find "$WORK/$s" -type f | wc -l | tr -d ' ')
  echo "  ✓ $s ($n 个文件)"
done

echo ""
echo "[2/6] G1 生成门(幂等 + 结构忠实)"
for s in react vue node java; do
  python3 lib/contract/cli.py verify "$CONTRACT" --stack "$s" >/dev/null
  echo "  ✓ $s"
done

echo ""
echo "[3/6] 跨栈一致性(后端/前端三方一致)"
python3 lib/contract/cli.py check "$CONTRACT" >/dev/null
echo "  ✓ 4 栈 manifest 覆盖一致"

echo ""
echo "[4/6] 状态机推进(唯一 transition 入口,门控闭环)"
SF="$WORK/state.json"
python3 lib/state_manager.py init "$SF" demo >/dev/null
R0='{"schema":"stage-subagent/v1","stage":"0","subagent":"orchestrator/init","token":"demo"}'
R1='{"schema":"stage-subagent/v1","stage":"1","subagent":"orchestrator/requirements-analyst","token":"demo"}'
R2='{"schema":"stage-subagent/v1","stage":"2","subagent":"contract/contract-designer","token":"demo"}'
R3='{"schema":"stage-subagent/v1","stage":"3","subagent":"orchestrator/services-analyst","token":"demo"}'
R4='{"schema":"stage-subagent/v1","stage":"4","subagent":"orchestrator/git-client","token":"demo"}'
R5A='{"schema":"stage-subagent/v1","stage":"5A","subagent":"codegen/node-codegen","token":"demo"}'
# 正常路径:start + complete(带产出与 receipt)
python3 lib/transition.py start "$SF" 0 >/dev/null
python3 lib/transition.py complete "$SF" 0 --receipt "$R0" --outputs '{"execution_plan":"demo"}' >/dev/null
# 契约已提供:显式带批准跳过需求/契约/方案/分支(演示模式)
python3 lib/transition.py skip "$SF" 1 --reason "契约已提供" --approved-by demo --receipt "$R1" >/dev/null
python3 lib/transition.py skip "$SF" 2 --reason "契约已提供" --approved-by demo --receipt "$R2" >/dev/null
python3 lib/transition.py skip "$SF" 3 --reason "演示模式" --approved-by demo --receipt "$R3" >/dev/null
python3 lib/transition.py skip "$SF" 4 --reason "演示模式" --approved-by demo --receipt "$R4" >/dev/null
# 完成后端实现(演示产出)
python3 lib/transition.py start "$SF" 5A >/dev/null
python3 lib/transition.py complete "$SF" 5A --receipt "$R5A" --outputs '{"changed_files":["node/api.ts"],"coverage":"demo"}' >/dev/null
# 绕过演示:无 receipt 的 complete 必须被阻断
if python3 lib/transition.py complete "$SF" 5B --outputs '{"changed_files":[],"coverage":"demo"}' >/dev/null 2>&1; then
  echo "  ✗ 无 receipt 竟然放行"
else
  echo "  ✓ 无 receipt 的 complete 被阻断(不可绕过)"
fi
python3 lib/state_manager.py summary "$SF" | python3 -c '
import json, sys
s = json.load(sys.stdin)
done = s["done"]
total = s["total"]
actionable = s["actionable"] or "(全部完成)"
print(f"  ✓ {done}/{total} 阶段完成, actionable={actionable}")
'

echo ""
echo "[5/6] 覆盖率门控"
python3 - <<'PY'
import sys; sys.path.insert(0, ".")
from lib.coverage_gate import check_coverage
for report in ({"changed_line": 45.0}, {"changed_line": 75.0}):
    r = check_coverage(report)
    print(f"  {report} -> {'PASS' if r['ok'] else 'BLOCK: ' + r['problems'][0]}")
PY

echo ""
echo "[6/6] 委派 fail-closed 校验(hook 统一 JSON 协议)"
if echo '{"stage":"2","receipt":null,"outputs":{"openapi_contract":"x"}}' | python3 hooks/delegation-guard >/dev/null 2>&1; then
  echo "  ✗ 意外放行"
else
  echo "  ✓ 无 receipt 被阻断(exit != 0)"
fi

echo ""
echo "=== 演示完成 ==="
