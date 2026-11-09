---
{
  "id": "qa-contract-conventions",
  "domain": "qa",
  "entity": "QaConvention",
  "type": "convention",
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

## 冒烟测试实操教训(zsh/macOS 本地环境)

- zsh 对未加引号的 `$VAR` 传参给 curl **不做分词**,header/JSON 会整体粘成
  一个参数导致 415/乱码——冒烟脚本一律写成 bash 文件再执行,不要行内拼。
- 起服前先探测端口占用(`lsof -ti:PORT`),残留进程会让新进程以
  "Port already in use" 静默失败,误判为构建问题。
- 断言前先确认响应包装形态(裸 DTO vs 统一包装),按契约而非习惯写解析。
- 断言失败先分层排查:请求是否真的送达(路径/方法/头)→ 响应体原文 →
  再下结论;本次项目多起"接口报错"实为脚本侧问题。
