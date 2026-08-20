# fe-be-contract-harness

前后端契约驱动 SDLC Harness —— 以 OpenAPI/Swagger 作为前后端**唯一事实源(SSOT)**,契约驱动生成 + 前后端一致性门控 + 多平台运行。

## 定位

- **范围**:完整 SDLC 自动化(需求 → 方案 → 编码 → 评审 → 测试 → 部署 → 交付)
- **前端**:React + Vue 双栈
- **后端**:Java(Spring) + Node(Nest) 双栈
- **契约**:OpenAPI 3.x 作为前后端唯一合同
- **平台**:CatPaw / CatClaw / Claude Code / Codex / OpenClaw / OpenCode

## 设计文档

完整设计见(同一工作区):

- `../learn/skills-for-regan/docs/architecture/fe-be-harness-design.md`

## 当前状态

已完成 **M0–M3**:仓库骨架、状态机/断点续跑、OpenAPI 契约解析、四栈(React/Vue/Java/Node)代码生成、G1 生成门、跨栈一致性校验与漂移检测。M4(评审/测试/部署/报告 + 多平台)尚未开始。

## 契约驱动生成用法

```bash
# 从契约生成指定技术栈的代码骨架
python3 lib/contract/cli.py generate examples/petstore.yaml --stack node --out gen/node
python3 lib/contract/cli.py generate examples/petstore.yaml --stack react --out gen/react

# G1 生成门校验(幂等 + 结构忠实)
python3 lib/contract/cli.py verify examples/petstore.yaml --stack node

# 跨栈一致性校验(后端/前端三方一致)
python3 lib/contract/cli.py check examples/petstore.yaml

# 契约漂移检测(fail-closed)
python3 lib/contract/cli.py drift examples/petstore.yaml --stack node --gen-dir gen/node

# 列出可用技术栈
python3 lib/contract/cli.py stacks
```

## 路线图

| 里程碑 | 交付物 | 状态 |
|--------|--------|------|
| M0 仓库骨架 | 目录骨架 + git + manifest + 最小校验 | ✅ |
| M1 契约驱动 | OpenAPI 解析 + 后端骨架 + 前端类型生成 | ✅ |
| M2 四栈适配 | 补齐 Vue + Java 适配器 | ✅ |
| M3 一致性门控 | consistency-checker + contract-drift-guard | ✅ |
| M4 完整 SDLC | 评审/测试/部署/报告 + 多平台验证 | 未开始 |

## 目录结构

```
fe-be-contract-harness/
├── harness-manifest.json      # 总清单:capabilities/lifecycle/依赖自愈
├── openclaw.plugin.json       # 平台描述符:hooks/skills 注册
├── agents/
│   ├── _shared/               # 共享规范模板
│   ├── orchestrator/          # 栈无关编排(planner/analyst/review…)
│   ├── contract/              # 契约层(designer/reviewer/consistency…)
│   ├── codegen/               # 执行层(react/vue/java/node codegen)
│   └── quality/               # 质量层(test/security/coverage)
├── hooks/                     # 事件拦截器(含 contract-drift-guard)
├── lib/
│   ├── planner/               # 路径规划
│   ├── stack/                 # 技术栈适配层(react/vue/java/node)
│   ├── contract/              # OpenAPI 解析/生成/一致性
│   └── platform/              # 平台适配
├── skills/  commands/  config/
├── evals/  tests/  .harness/
```

## 开发

```bash
npm run validate   # 校验 manifest 引用完整性
npm test           # 冒烟测试
npm run check      # 校验 + 冒烟
```

> 依赖:python3 ≥ 3.8(校验脚本运行时)。
