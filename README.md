# fe-be-contract-harness

前后端**契约驱动 + SDD(规范驱动开发)** Harness —— 以 OpenAPI/Swagger 作为前后端**唯一事实源(SSOT)**,契约驱动生成 + 前后端一致性门控 + 结构化需求 Spec + 多平台运行。

## 定位

- **范围**:完整 SDLC(需求 → 方案 → 编码 → 评审 → 测试 → 部署 → 交付)
- **前端**:React + Vue 双栈
- **后端**:Java(Spring) + Node(Nest) 双栈
- **契约**:OpenAPI 3.x 作为前后端唯一合同
- **平台**:CatPaw / CatClaw / Claude Code / Codex / OpenClaw / OpenCode

## 设计文档

完整设计见(同一工作区):

- `../learn/skills-for-regan/docs/architecture/fe-be-harness-design.md`(§0–§19)

## 能力全景

| 类别 | 能力 | 实现 |
|------|------|------|
| **契约驱动** | OpenAPI 解析、四栈 codegen、G1 生成门、跨栈一致性、漂移检测 | `lib/contract/` + `lib/stack/` |
| **SDD** | 结构化需求 Spec、领域知识库、仓库知识库、可行性验证、经验沉淀 | `lib/requirements_spec.py` / `domain_knowledge.py` / `repo_knowledge.py` / `feasibility.py` / `experience.py` |
| **执行/门控** | FSM、状态机/断点续跑、委派协议、checkpoint、覆盖率门控+采集 | `lib/workflow_fsm.py` / `state_manager.py` / `delegation.py` / `checkpoint_manager.py` / `coverage_gate.py` / `coverage_collector.py` |
| **编排/韧性** | 编排 runner、路径规划、波次并行、上下文编排、智能重试、依赖自愈、通知 | `lib/runner.py` / `planner/` / `parallel_wave_scheduler.py` / `context_orchestrator.py` / `smart_retry.py` / `self_heal.py` / `notifier.py` |
| **代码理解** | 代码知识图、双审查员评审+四源聚合 | `lib/code_graph.py` / `code_review.py` |
| **智能层** | 25 个 agent(富 prompt + references)、3 skills、6 commands、8 hooks | `agents/` / `skills/` / `commands/` / `hooks/` |

## 快速上手

```bash
# 契约驱动生成
python3 lib/contract/cli.py generate examples/petstore.yaml --stack node --out gen/node
python3 lib/contract/cli.py verify examples/petstore.yaml --stack node   # G1 生成门
python3 lib/contract/cli.py check examples/petstore.yaml                  # 跨栈一致性
python3 lib/contract/cli.py drift examples/petstore.yaml --stack node --gen-dir gen/node

# 编排 runner(确定性阶段真实执行,LLM 阶段签发委派指令;终态一律经 transition 门控)
python3 lib/runner.py run examples/petstore.yaml --out gen --state state.json
python3 lib/runner.py run examples/petstore.yaml --out gen --state state.json --auto   # 演示自动模式

# 唯一状态迁移入口(FSM + 前置 + 产出 + receipt + checkpoint + evidence 全门控)
python3 lib/transition.py start state.json 0
python3 lib/transition.py complete state.json 0 --receipt '<json>' --outputs '<json>'
python3 lib/transition.py skip state.json 1 --reason "契约已提供" --approved-by <who> --receipt '<json>'
python3 lib/transition.py fail state.json 5A --reason "<原因>"
python3 lib/transition.py retry state.json 5A
python3 lib/state_manager.py summary state.json          # 进度汇总(只读)

# 端到端演示(四栈生成 → G1 门 → 一致性 → transition 门控闭环)
npm run demo

# 结构化需求 Spec 校验 / 模糊点识别 / 可行性验证
python3 -c "from lib.requirements_spec import validate_requirements_completion; ..."
python3 lib/domain_knowledge.py gaps <spec.json>
python3 lib/feasibility.py <spec.json> <repo>

# 仓库/领域知识冷启动
python3 lib/repo_knowledge.py scaffold <repo> --name <项目名>
python3 lib/domain_knowledge.py seed business order "..."
```

## 门控闭环(第一阶段)

任何阶段到达终态(completed / skipped)必须经过 `lib/transition.py`,形成不可绕过的执行链:

1. **FSM 转换合法性** —— 非法状态转换直接拒绝
2. **前置就绪** —— DAG 前置阶段全部终态才可推进(并行汇合自动处理)
3. **必需产出** —— `required_outputs` 缺失即阻断(Stage 1 含结构化 Spec 硬校验)
4. **委派 fail-closed** —— dispatch receipt 有效且 subagent 匹配
5. **checkpoint 人工卡点** —— mandatory_review 不可 skip;approve/skip 才可终态,revise 回到 running
6. **审计落盘** —— outputs / receipt / checkpoint / evidence / completed_at 随状态原子写入

> `state_manager.set_stage_state` 仅为低层运维写(恢复/调试),不参与正式流程。
> hooks 统一走 JSON event protocol:`echo '<事件JSON>' | hooks/<guard>`,输出 `{"allow": bool, ...}`。

## 测试

`npm test` 全绿:**26 套确定性自测(含 transition 门控闭环 + hooks 协议)+ agent 完整性校验(25 agents)+ eval 评测**。

```bash
npm run validate   # 校验 manifest JSON
npm test           # 全量冒烟(24 套自测)
npm run check      # 校验 + 冒烟
npm run demo       # 端到端演示
```

## 目录结构

```
fe-be-contract-harness/
├── harness-manifest.json / openclaw.plugin.json / .claude-plugin/   # 平台描述符
├── agents/          # 25 个智能体(orchestrator/contract/codegen/quality + _shared)
├── hooks/           # 8 个事件拦截器(contract-drift/delegation/checkpoint/coverage/...)
├── skills/          # 3 个 skill(主 workflow + build-repo-knowledge + build-domain-knowledge)
├── commands/        # 6 个斜杠命令
├── lib/             # 确定性内核(~35 模块:contract/stack/planner + SDD + 编排韧性)
├── config/          # delegation-policy / contract-spec / coverage-config / domain-knowledge / experience
├── examples/        # 示例契约(petstore.yaml)
├── evals/           # 评测集(cases + runner)
└── tests/           # 24 套确定性自测
```

## 现状与边界

- ✅ **确定性内核完整**:契约→生成→门控→一致性→漂移→委派→checkpoint→覆盖率,全链路可测可跑
- ✅ **SDD 前半段打通**:领域/仓库知识 → 模糊点识别 → 可行性验证 → 结构化 Spec(硬门控)
- ⚠️ **待接真实运行时**:LLM 阶段(需求分析/契约设计/评审)由 agent 定义 + 确定性 runner 驱动,但真实 LLM 派发需接 CatPaw/Claude Code/OpenClaw 运行时
- ⚠️ **OpenAPI 解析是子集**:支持 `$ref`/array/object/enum/基础类型,`allOf/oneOf/anyOf` 待扩展

## 依赖

- python3 ≥ 3.8 + pyyaml(解析 YAML 契约)
- node ≥ 18(可选,前端栈构建)

> 参考 super-assistant 设计,差异化在「契约驱动 + SDD」;详见设计文档。
