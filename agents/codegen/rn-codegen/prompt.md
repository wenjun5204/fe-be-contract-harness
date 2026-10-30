<!-- Base: agents/_shared/base-prompt.md -->

# React Native / Expo 代码生成器(rn-codegen)

从 `openapi.yaml` 生成 React Native(及 Expo 托管工作流)前端骨架:TS 类型 + fetch 请求层。
两种栈的生成产物完全同构,仅工程命令映射与部署路由不同。

## 执行(确定性生成器)

```bash
# 裸 RN 工程(ios/android 原生目录)
python3 lib/contract/cli.py generate <contract> --stack react_native --out <out_dir>
python3 lib/contract/cli.py verify <contract> --stack react_native   # G1 生成门

# Expo 托管工程(app.config.js / app.config.ts)
python3 lib/contract/cli.py generate <contract> --stack expo --out <out_dir>
python3 lib/contract/cli.py verify <contract> --stack expo           # G1 生成门
```

## 约束

- 生成幂等;生成区(「勿手改」)与人工区分离,重生成不覆盖人工代码
- 业务逻辑由人工在 `// TODO` 处填充,不改动结构(类型签名 / 请求层签名)
- 请求层可直接使用 RN 全局 fetch 实现,或封装为 hooks(useXxx)
- 本地确定性门只到 lint(eslint + tsc)/ build(tsc 类型检查)/ test(jest);
  真机 metro bundle、EAS 构建、应用商店发布归 CI/发布阶段,harness 只登记部署路由
- Expo prebuild 出的 ios/android 目录会同时命中 react_native 栈的工程识别,
  以 detect evidence 中的 app.config.* 区分
