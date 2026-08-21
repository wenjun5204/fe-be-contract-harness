<!-- Base: agents/_shared/base-prompt.md -->

# React 代码生成器(react-codegen)

从 `openapi.yaml` 生成 React 前端骨架:TS 类型 + API 请求层。

## 执行(确定性生成器)

```bash
python3 lib/contract/cli.py generate <contract> --stack react --out <out_dir>
python3 lib/contract/cli.py verify <contract> --stack react   # G1 生成门
```

## 约束

- 生成幂等;生成区(「勿手改」)与人工区分离,重生成不覆盖人工代码
- 业务逻辑由人工在 `// TODO` 处填充,不改动结构(类型签名 / 请求层签名)
- 请求层可直接使用或封装为 hooks(useXxx)
