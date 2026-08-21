<!-- Base: agents/_shared/base-prompt.md -->

# 状态管理器(state-manager)

用确定性状态管理器读写 pipeline 状态(断点续跑)。

## 执行

```bash
python3 lib/state_manager.py init <state.json> <change_id>
python3 lib/state_manager.py set-state <state.json> <stage> completed
python3 lib/state_manager.py actionable <state.json>   # 下一可推进阶段
python3 lib/state_manager.py summary <state.json>
```
