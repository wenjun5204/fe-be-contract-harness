---
{
  "id": "order-core",
  "domain": "business",
  "entity": "Order",
  "type": "lifecycle",
  "status": "confirmed",
  "source": "user_document",
  "fields": [
    {"name": "orderId", "type": "string", "required": true},
    {"name": "status", "type": "string", "required": true},
    {"name": "amount", "type": "integer", "required": true, "unit": "fen"},
    {"name": "createdAt", "type": "datetime", "required": true},
    {"name": "freight", "type": "integer", "required": false, "unit": "fen"}
  ],
  "states": ["PENDING", "PAID", "SHIPPED", "CANCELLED"],
  "error_codes": [
    {"code": 409, "meaning": "重复订单（幂等冲突）"},
    {"code": 422, "meaning": "状态流转非法"}
  ]
}
---

# 订单领域知识

## 业务规则

- 订单幂等：同 `Idempotency-Key` 重复提交返回原订单，不重复创建。
- 取消订单须在 `SHIPPED` 前；已发货订单不可取消。
- 金额字段统一使用 `amount`，单位为分，不使用 `price`。
- 订单金额不含运费，运费使用独立字段 `freight`。

## 已确认范围

- 本条目适用于订单创建、查询、取消及其前后端契约、测试验收。
