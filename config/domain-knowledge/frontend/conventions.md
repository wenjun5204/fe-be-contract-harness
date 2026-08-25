---
{
  "id": "frontend-contract-conventions",
  "domain": "frontend",
  "entity": "FrontendContractConvention",
  "type": "convention",
  "status": "confirmed",
  "source": "user_document",
  "fields": [],
  "states": [],
  "error_codes": []
}
---

# 前端约定

- 请求层统一从契约派生，不手改生成结果；业务组件通过 hooks 消费请求能力。
- 接口 mock 使用契约派生的 MSW，不手写脱离契约的 mock。
- 状态字段展示必须使用枚举映射，例如 `PENDING` 映射为“待支付”。
