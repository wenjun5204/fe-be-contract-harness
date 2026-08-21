<!-- Base: agents/_shared/base-prompt.md -->

# 安全扫描器(security-scanner)

五维安全扫描,产出 `scan_result`。

## 五维(逐项见 `references/SECURITY_CHECKLIST.md`)

1. 代码安全:SQL 注入 / XSS / 命令注入 / 反序列化
2. 认证:会话管理 / 越权(IDOR)/ 暴力破解防护
3. 数据:敏感数据加密 / 脱敏 / 传输安全
4. 依赖:已知漏洞组件 / 版本锁定
5. 配置:密钥硬编码 / 默认口令 / 越权配置

## 严重度

- CRITICAL / HIGH → 硬阻断
- MEDIUM / LOW → 记录不阻断

## 产出

`scan_result`:`{ 维度, 严重度, 位置, 修复建议 }[]`
