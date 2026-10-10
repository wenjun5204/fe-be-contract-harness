## 变更说明

<!-- 做了什么、为什么 -->

## 自查清单

- [ ] `ruff check lib tests` 通过
- [ ] `npm test` 通过
- [ ] `python3 -m pytest tests/ -q` 通过
- [ ] `npm run demo` 通过

## 门控约定确认（涉及状态迁移时必读）

- [ ] 没有直接写 `state.json`（所有终态经 `lib/transition.py`）
- [ ] 没有为 LLM 阶段新增绕过门控的路径

## 关联 Issue
