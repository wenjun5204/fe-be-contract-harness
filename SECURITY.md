# 安全策略

## 报告漏洞

发现安全问题请勿公开 Issue。通过 [GitHub Security Advisories](https://github.com/wenjun5204/fe-be-contract-harness/security/advisories/new) 私下报告，或发邮件到仓库 owner。会在 72 小时内响应。

## 支持版本

| 版本 | 支持 |
|---|---|
| main / 最新 tag | ✅ |

## 安全边界（使用前请阅读）

本 harness 的设计假设和已知边界：

1. **LLM 网关凭据**：`--live --llm-runtime openai` 读取环境变量 `OPENAI_API_KEY` / `OPENAI_BASE_URL`。凭据只进进程内存和请求头，不会写入状态文件或日志；但请勿把含凭据的输出重定向到共享位置。
2. **仓库知识扫描**：`lib/repo_knowledge.py build` 是确定性本地扫描，不上传数据。但生成的 `.agents/` 文档可能包含你业务仓库的目录结构、技术栈和约定——开源前请自行确认这些内容是否可公开。
3. **receipt 语义**：单机/单运行时演示语义，token 为 runner 签发的标识，**不防恶意进程**。跨进程/分布式场景需替换为真随机 token 与签名机制。
4. **生成代码不包含鉴权**：四栈生成产出的是契约骨架（DTO、路由、客户端类型），不含鉴权、输入消毒等安全逻辑，直接上线前必须自行补全。
5. **运行时契约校验**：`cli.py live` 会向你指定的 URL 发请求，URL 来自命令行参数，注意不要指向生产库的写接口（OpenAPI 文档端点应为只读）。
