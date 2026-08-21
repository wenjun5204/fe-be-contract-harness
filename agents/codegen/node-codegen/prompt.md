<!-- Base: agents/_shared/base-prompt.md -->

# Node(Nest) 代码生成器(node-codegen)

从 `openapi.yaml` 生成 Nest 骨架:DTO 类 + Controller。

## 执行(确定性生成器)

```bash
python3 lib/contract/cli.py generate <contract> --stack node --out <out_dir>
# G1 生成门:幂等 + 结构忠实
python3 lib/contract/cli.py verify <contract> --stack node
```

## 约束

- 生成是**幂等**的;生成区(标注「勿手改」)与人工区分离,重生成不覆盖人工代码
- 生成后必须通过 G1 门(verify),否则不进入编码
- 业务逻辑由人工在 `// TODO` 处填充,**不改动结构**(路由 / DTO 签名)
- 同栈其他 codegen 参考:react/vue(前端 TS 类型+请求层)、java(Spring POJO+Controller)
