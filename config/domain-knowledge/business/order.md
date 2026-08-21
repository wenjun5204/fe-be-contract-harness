# 订单领域知识(business)

> 供 requirements-analyst 做「基于领域知识识别模糊点」。知识即约定,澄清结论沉淀于此。

## 实体与字段约定

- Order(订单):orderId / status / amount / createdAt
- 金额字段统一用 `amount`(单位:分),不用 `price`
- 状态枚举:PENDING / PAID / SHIPPED / CANCELLED

## 业务规则

- 订单幂等:同 Idempotency-Key 重复提交返回原订单(不重复创建)
- 取消订单须在 SHIPPED 前;已发货不可取消

## 错误码约定

- 409:重复订单(幂等冲突)
- 422:状态流转非法(如已发货取消)

## 已知模糊点(历史澄清记录)

- "订单金额是否含运费" → 已确认:不含,运费单独字段 freight
