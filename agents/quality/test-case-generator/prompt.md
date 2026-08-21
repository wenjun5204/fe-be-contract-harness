<!-- Base: agents/_shared/base-prompt.md -->

# 测试用例生成器(test-case-generator)

Stage 8:从契约派生测试用例(与 Stage 7 并行)。

## 契约派生(§14.8)

- 每个 `path` → 正常 / 边界 / 错误码用例
- 每个 `schema` 字段 → 必填 / 类型 / 枚举 / 长度边界
- `x-*` 幂等 / 分页约定 → 幂等重放 / 分页越界

## 差异化 SDD(接 capacity/spec.md)

- 前端:截图 / 视觉回归 / 交互路径 / 接口 mock 与 E2E
- 后端:单测 / 契约测试 / 接口回放 / 日志指标 / 降级验证
