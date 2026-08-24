---
name: fe-be-contract-workflow
description: 前后端契约驱动 SDLC 工作流。触发词:前后端开发、契约驱动、openapi、从契约生成、接口开发、全流程开发、契约一致性、fe-be-harness。当用户要基于 OpenAPI 契约做前后端并行开发,或需要契约驱动生成代码骨架 + 一致性门控时使用。
allowed-tools: Read, Write, Bash, TodoWrite
---

# 前后端契约驱动 SDLC 工作流

以 OpenAPI 契约为**唯一事实源(SSOT)**的前后端全流程自动化:需求 → 契约 → 编码 → 一致性校验 → 评审 → 测试 → 部署 → 交付。

## 触发条件

- 用户提供 OpenAPI 契约,或要求「契约驱动 / 从契约生成」前后端代码
- 前后端并行开发,需要保证两端一致
- 需要 12 阶段全流程编排(或指定阶段)

## 工作流(12 阶段)

| 阶段 | 名称 | 关键动作 |
|------|------|----------|
| 0 | 初始化 | init state.json |
| 1 | 需求分析 | requirements-analyst 🔴 |
| 2 | 接口契约设计 | contract-designer 产出 openapi.yaml 🔴 |
| 3 | 仓库识别与技术方案 | services-analyst 🔴 |
| 4 | 分支管理 | git-client |
| 5A/5B | 后端/前端实现(并行) | node/java + react/vue codegen |
| 6 | 一致性校验 | consistency-checker 🔴 |
| 7/8 | 提交PR / 测试用例(并行) | code-review + test-case-generator |
| 9 | 提测部署 | deployer |
| 10 | 交付报告 | notifier |

> 🔴 = mandatory_review(强制人工确认)

## 核心命令(确定性内核)

```bash
python3 lib/contract/cli.py generate <contract> --stack node --out gen/node   # 生成骨架
python3 lib/contract/cli.py verify <contract> --stack node                     # G1 生成门
python3 lib/contract/cli.py check <contract>                                   # 跨栈一致性
python3 lib/contract/cli.py drift <contract> --stack node --gen-dir gen/node   # 漂移检测
python3 lib/contract/cli.py stacks                                             # 可用技术栈
python3 lib/state_manager.py init <state.json> <change_id>                     # 状态初始化
python3 lib/transition.py complete <state.json> <stage> --receipt '<json>' --outputs '<json>'  # 唯一完成入口
python3 lib/runner.py run <contract> --out gen --state state.json              # 编排(LLM 阶段只签发指令)
bash lib/scripts/demo-end-to-end.sh                                            # 端到端演示
```

## 核心约束

1. `openapi.yaml` 是唯一事实源;偏离契约必须先走契约 diff + Stage 2 checkpoint 重新签字
2. 主 Agent 只调度,每个阶段派发给独立子 Agent(上下文隔离,契约是跨子 Agent 唯一接口)
3. 覆盖率 ≥60% + 契约一致性双门控,fail-closed
4. 生成幂等,生成区(「勿手改」)与人工区分离
5. 断点续跑:`python3 lib/state_manager.py` 支持任意阶段恢复

## 子 Agent 委派

每阶段按 `config/delegation-policy.json` 派发到对应 subagent;dispatch 前签发 receipt,
`delegation-guard` fail-closed 校验(阶段必需 / receipt 有效 / subagent 匹配 / 产出完整)。
