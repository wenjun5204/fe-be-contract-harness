---
{
  "id": "qa-contract-conventions",
  "domain": "qa",
  "entity": "QaConvention",
  "type": "qa-case",
  "status": "confirmed",
  "source": "user_document",
  "fields": [],
  "states": [],
  "error_codes": []
}
---

# QA 约定

- 接口用例从契约派生；每个端点至少覆盖正常、边界与错误码场景。
- 验收覆盖接口响应、DB 数据、日志和副作用四个维度。
- 前端验收包含截图比对和完整交互路径。
