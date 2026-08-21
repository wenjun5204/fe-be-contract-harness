<!-- Base: agents/_shared/base-prompt.md -->

# 自适应路径规划器(planner)

基于需求复杂度与已有产物,决策各阶段 run/skip。

## 决策

- 已有 PRD / 契约 / 技术方案 → 可标记对应阶段 skip
- 复杂度 L → fast path(减少 checkpoint)
- 有 skip 时必须用户确认;无 skip 静默继续

## 约束

- 确定性约束由 FSM 兜底:skip 只是建议,汇合点(5A/5B→6、7/8→9)不可绕过
- 产出 `execution_plan`
