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

| 阶段 | 名称 | 关键动作 | 委派角色(dispatch --subagent 传此名) |
|------|------|----------|----------------|
| 0 | 初始化 | init state.json | `orchestrator/init` |
| 1 | 需求分析 | 产出结构化需求 Spec 🔴 | `orchestrator/requirements-analyst` |
| 2 | 接口契约设计 | contract-designer 产出 openapi.yaml 🔴 | `contract/contract-designer` |
| 3 | 仓库识别与技术方案 | services-analyst 🔴 | `orchestrator/services-analyst` |
| 4 | 分支管理 | git-client | `orchestrator/git-client` |
| 5A/5B | 后端/前端实现(DAG 上逻辑并行,执行一律串行) | codegen | java: `codegen/java-codegen`,node: `codegen/node-codegen`,react: `codegen/react-codegen`,vue: `codegen/vue-codegen` |
| 6 | 一致性校验 | consistency-checker 🔴 | `contract/consistency-checker` |
| 7 | 提交PR | code-review | `quality/code-review` |
| 8 | 测试用例 | test-case-generator | `quality/test-case-generator` |
| 9 | 提测部署 | deployer | `orchestrator/deployer` |
| 10 | 交付报告 | notifier | `orchestrator/notifier` |

> 🔴 = mandatory_review(强制人工确认)
> 角色名与 config/delegation-policy.json 一一对应;`start`/`dispatch` 会返回各阶段 allowed_subagents,不匹配时报错附带 did-you-mean 候选。
>
> **执行模型(MVP:串行)**:DAG 中的并行分支(5A/5B、7/8)仅表示前置关系上可同时 actionable,
> 实际执行一律串行推进(先 5A 后 5B,先 7 后 8)。原因:共享 git working tree 避免写冲突、
> 后阶段可吃到前阶段真实产出、checkpoint 人工交互保持单一活跃阶段。任意时刻拿不准下一步,
> 跑 `python3 lib/transition.py hint <state>` 获取导航。未来如需真并行,需将 current_stage
> 单值改为 active_stages 集合并限定仅目录不相交的阶段对开放(5A/5B),7/8 永远串行。

## 核心命令(确定性内核)

```bash
python3 lib/contract/cli.py generate <contract> --stack node --out gen/node   # 生成骨架
python3 lib/contract/cli.py verify <contract> --stack node                     # G1 生成门
python3 lib/contract/cli.py check <contract>                                   # 跨栈一致性
python3 lib/contract/cli.py drift <contract> --stack node --gen-dir gen/node   # 漂移检测(骨架层)
python3 lib/contract/cli.py live <contract> --url http://127.0.0.1:8080/v3/api-docs  # 运行时校验(抓序列化漂移,如 isMine→mine)
python3 lib/contract/cli.py stacks                                             # 可用技术栈
python3 lib/state_manager.py init <state.json> <change_id>                     # 状态初始化
python3 lib/transition.py dispatch <state.json> <stage> --subagent <角色名>    # 一键委派:签发+登记+start(receipt 落盘 receipts/,预校验角色)
python3 lib/transition.py complete <state.json> <stage> --receipt-file <f> --outputs-file <f> [--checkpoint approve]  # 唯一完成入口(大 JSON 用 -file 传)
python3 lib/runner.py run <contract> --out gen --state state.json              # 编排(LLM 阶段只签发指令)
bash lib/scripts/demo-end-to-end.sh                                            # 端到端演示
```

> evidence 结构化约定:每条必须有 `type`;可选 `command`/`exit_code`(非零阻断)/`artifact_path`(必须真实存在,相对仓库根)。
> Stage 9 的 `deploy_result` 必须是结构化对象(不接受自由文本):`{"environment", "ok", "health_check": {"status_code"}, "smoke_tests": [{"name", "status_code", "passed"}]}`,非 2xx / ok=false / passed=false 均阻断。

## 核心约束

1. `openapi.yaml` 是唯一事实源;偏离契约必须先走契约 diff + Stage 2 checkpoint 重新签字
2. 主 Agent 只调度,每个阶段派发给独立子 Agent(上下文隔离,契约是跨子 Agent 唯一接口)
3. 覆盖率 ≥60% + 契约一致性双门控,fail-closed
4. 生成幂等,生成区(「勿手改」)与人工区分离
5. 断点续跑:`python3 lib/state_manager.py` 支持任意阶段恢复

## 子 Agent 委派

每阶段按 `config/delegation-policy.json` 派发到对应 subagent;dispatch 前签发 receipt,
`delegation-guard` fail-closed 校验(阶段必需 / receipt 有效 / subagent 匹配 / 产出完整)。
