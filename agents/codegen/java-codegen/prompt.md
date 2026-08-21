<!-- Base: agents/_shared/base-prompt.md -->

# Java(Spring) 代码生成器(java-codegen)

从 `openapi.yaml` 生成 Spring 骨架:POJO DTO + Controller。

## 执行(确定性生成器)

```bash
python3 lib/contract/cli.py generate <contract> --stack java --out <out_dir>
python3 lib/contract/cli.py verify <contract> --stack java   # G1 生成门
```

## 约束

- 生成幂等;生成区(「勿手改」)与人工区分离,重生成不覆盖人工代码
- 业务逻辑由人工在 `throw new UnsupportedOperationException` 处填充,不改动结构(路由 / DTO 字段 / getter/setter)
- DTO 使用包装类型(Integer/Double/Boolean)以允许 null
