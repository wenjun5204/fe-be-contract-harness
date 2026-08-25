---
{
  "id": "backend-api-conventions",
  "domain": "backend",
  "entity": "ApiConvention",
  "type": "convention",
  "status": "confirmed",
  "source": "user_document",
  "fields": [],
  "states": [],
  "error_codes": [
    {"code": 400, "meaning": "参数错误"},
    {"code": 409, "meaning": "冲突"},
    {"code": 422, "meaning": "业务校验失败"}
  ]
}
---

# 后端约定

- Controller 只做参数校验与路由，业务逻辑位于 Service 层。
- 写操作（POST / PUT / PATCH）必须通过 `Idempotency-Key` 保证幂等。
- 错误码统一：400 参数错误、409 冲突、422 业务校验失败。
