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

## 响应包装约定(实战教训)

成功响应是**裸 DTO**(`{"familyName":...}`),不包 `code/data` 外壳;只有错误
走统一错误体(业务码 40000/40100/40300/40400/40900/50000 + message,由
`@ControllerAdvice` 落地)。契约 SSOT 里怎么写,客户端就怎么解析——切忌按
习惯假设"成功也带 code 字段",冒烟脚本先读契约再写断言。

## 平台托管环境:微信云托管(实战教训)

- 身份链路:小程序 `wx.cloud.callContainer` → 平台注入 `X-WX-OPENID`
  (不可伪造)→ AuthService 落库;**服务不得开启公网访问路径**,否则该头可被
  外部伪造(尤其鉴权用 token=userId 明文的演示级方案时)。
- 本地 H2 与生产 MySQL 行为差异:MySQL 严格拒绝只读事务内写库(H2 不拒绝,
  本地测试发现不了)——`@Transactional(readOnly=true)` 方法内不得有任何兜底
  save;兜底异常处理器打全量堆栈,禁止吞异常。
- 缩容到 0 的容器 + JVM 服务冷启动 5-20s:控制台最小实例数≥1 可根治,
  前端须按"缓存先行"模式兜底(见 frontend conventions)。
