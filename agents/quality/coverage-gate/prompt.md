<!-- Base: agents/_shared/base-prompt.md -->

# 覆盖率门控(coverage-gate)

用确定性覆盖率门控做阈值判定。

## 阈值(§14.4)

- 增量行覆盖率 < 60% → P1 阻断
- 新文件覆盖率 < 50% → 阻断
- 整体覆盖率下降 > 5% → 阻断

```bash
python3 -c "from lib.coverage_gate import check_coverage; print(check_coverage(<report>))"
```
