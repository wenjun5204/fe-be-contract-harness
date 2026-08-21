# 后端约定(backend)

> 后端方向领域知识:接口/错误码/幂等约定。

## 约定

- Controller 只做参数校验与路由,业务在 Service 层
- 写操作(POST/PUT/PATCH)必须幂等(Idempotency-Key)
- 错误码统一:400 参数 / 409 冲突 / 422 业务校验
