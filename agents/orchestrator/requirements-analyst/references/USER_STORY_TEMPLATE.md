# 用户故事模板

## 格式

```
**As a** <角色>
**I want** <功能>
**So that** <价值>

### Acceptance Criteria
- [ ] Given <前置条件>, when <操作>, then <预期结果>

### Notes
- 假设:...
- 依赖:...
```

## INVEST 标准

| 字母 | 含义 |
|------|------|
| I | Independent 独立 |
| N | Negotiable 可协商 |
| V | Valuable 有价值 |
| E | Estimable 可估算 |
| S | Small 小(一个迭代可完成) |
| T | Testable 可测试 |

## 示例

**As a** 登录用户
**I want** 在商品列表按价格排序
**So that** 我能快速找到预算内的商品

### Acceptance Criteria
- [ ] Given 商品列表有数据,when 点击「价格」排序,then 列表按价格升序排列
- [ ] Given 已升序,when 再次点击「价格」,then 切换为降序
- [ ] Given 存在价格为空商品,when 排序,then 空价格商品排在最后
