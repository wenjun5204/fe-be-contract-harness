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
echo "[4/6] 状态机推进(模拟 Stage 0→10)"
SF="$WORK/state.json"
python3 lib/state_manager.py init "$SF" demo >/dev/null
for sid in 0 1 2 3 4 5A 5B 6 7 8 9 10; do
  python3 lib/state_manager.py set-state "$SF" "$sid" completed >/dev/null
done
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
echo "[6/6] 委派 fail-closed 校验"
if python3 hooks/delegation-guard 2 null null >/dev/null 2>&1; then
  echo "  ✗ 意外放行"
else
  echo "  ✓ 无 receipt 被阻断(exit != 0)"
fi

echo ""
echo "=== 演示完成 ==="
