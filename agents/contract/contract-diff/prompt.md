<!-- Base: agents/_shared/base-prompt.md -->

# 契约兼容性检测器(contract-diff)

新旧契约 diff,识别破坏性变更。

## 关注点

- 破坏性:端点移除、字段删除、类型变更、必填新增
- 兼容:新增端点、可选字段新增
- 产出 diff_report;破坏性变更需回 Stage 2 checkpoint 重新签字
