<!-- Base: agents/_shared/base-prompt.md -->

# 两段式初始化器(init)

Stage 0:初始化状态与执行计划。

## 执行

```bash
# 按 DAG 初始化全阶段 pending 的 state.json
python3 lib/state_manager.py init <state.json> <change_id>
```

## 产出

- 写入 `state.json`(全阶段 pending)
- `execution_plan`:默认执行全部 12 阶段(0→1→2→3→4→5A/5B→6→7/8→9→10)
- 后续 planner 可覆盖此计划
