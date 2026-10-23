# Harness 工程化设计架构

> 目的：一页梳理整个 harness 的分层、数据流与设计不变量。
> 配套：改造路线图见 [HARNESS_UPGRADE.md](../HARNESS_UPGRADE.md)；门控循环图见 [gate-loop.svg](gate-loop.svg)。

---

## 一、分层总览

```mermaid
flowchart TB
    subgraph 入口层
        CLI["CLI 入口<br/>lib/runner.py<br/>lib/contract/cli.py"]
        Hooks["平台 Hooks(守卫)<br/>hooks/*-guard"]
        Skills["Skills / Agents<br/>skills/ agents/ commands/"]
    end

    subgraph 编排层["编排层(主 Agent 只调度)"]
        Runner["runner.py<br/>波次调度 · planner 路径决策<br/>幂等 resume · self_heal 自检"]
        PWS["parallel_wave_scheduler<br/>5A/5B 同波并行"]
        Planner["planner<br/>run/skip 数据驱动"]
    end

    subgraph 执行层["执行层(--live)"]
        Dispatch["llm_dispatch.py<br/>tool calling 主循环"]
        Condenser["condenser 确定性压缩"]
        Retry["smart_retry 退避重试"]
        Tools["tool_registry<br/>8 个工具(ACI 紧凑输出)"]
    end

    subgraph 门控层["门控层(唯一终态入口)"]
        Transition["transition.py<br/>FSM/前置/产出/receipt/<br/>checkpoint/evidence 六门<br/>+ RLock 并发串行化"]
    end

    subgraph 知识层["知识层(推 + 拉)"]
        CtxOrch["context_orchestrator<br/>按 Stage/实体/预算组上下文"]
        DomainKB["domain_knowledge.py<br/>config/domain-knowledge/"]
        RepoKB["repo_knowledge.py<br/>目标仓库 .agents/docs/"]
        Exp["experience.py<br/>失败教训闭环(写→读)"]
    end

    subgraph 契约内核["契约内核(确定性,零 LLM)"]
        Parser["parser.py"]
        Gen["generator.py<br/>+ manifest sha256"]
        Verify["verify.py(G1)"]
        Cons["consistency.py(跨栈)"]
        Drift["live_check.py(漂移)"]
        Stacks["stack/{react,vue,node,java}"]
    end

    subgraph 持久层
        State["state.json<br/>(原子写 tmp+rename)"]
        Events["events.jsonl<br/>(事件溯源)"]
        Transcripts["transcripts/<br/>(--live trajectory)"]
    end

    CLI --> Runner
    Hooks --> Transition
    Skills --> Runner
    Runner --> PWS --> Dispatch
    Runner --> Planner
    Runner --> Stacks
    Runner --> Transition
    Dispatch --> Condenser
    Dispatch --> Retry
    Dispatch --> Tools
    Dispatch --> CtxOrch
    Dispatch --> Transition
    CtxOrch --> DomainKB
    CtxOrch --> RepoKB
    Dispatch <-->|"失败写入 / 启动检索"| Exp
    Parser --> Gen --> Verify
    Gen --> Stacks
    Verify --> Cons
    Parser --> Drift
    Transition --> State
    Runner -->|"每条事件即时落盘"| Events
    Dispatch --> Transcripts
```

## 二、12 阶段工作流与波次

```mermaid
flowchart LR
    S0["0 初始化"] --> S1["1 需求分析 ⏸"]
    S1 --> S2["2 契约设计 ⏸"]
    S2 --> S3["3 技术方案 ⏸"]
    S3 --> S4["4 分支管理"]
    S4 --> W["并行波次"]
    W --> S5A["5A 后端生成"]
    W --> S5B["5B 前端生成"]
    S5A --> S6["6 一致性校验 ⏸"]
    S5B --> S6
    S6 --> S7["7 提交与 PR ⏸"]
    S6 --> S8["8 测试用例 ⏸"]
    S7 --> S9["9 提测部署 ⏸"]
    S8 --> S9
    S9 --> S10["10 交付报告 ⏸"]
```

- ⏸ = checkpoint（1/2/3/6 是 `mandatory_review`，7/8/9/10 是 `artifact_review`）
- **确定性阶段**（0/5A/5B/6/10）本地执行；**LLM 阶段**（1/2/3/4/7/8/9）默认签发 directive，`--live` 才真实执行
- 5A/5B 无依赖 → `parallel_wave_scheduler` 同波并行，汇合点 6/9 不可跳过（FSM 兜底）

## 三、门控链（唯一终态入口）

```mermaid
flowchart TB
    A["阶段要达终态"] --> B{"1. FSM 合法性<br/>(pending→start / running→complete)"}
    B -->|不合法| X["TransitionError → blocked"]
    B --> C{"2. 前置就绪<br/>all_prereqs_completed"}
    C -->|未就绪| X
    C --> D{"3. required_outputs<br/>完整 + 语义校验"}
    D -->|缺失| X
    D --> E{"4. receipt fail-closed<br/>登记/匹配/未消费"}
    E -->|伪造| X
    E --> F{"5. checkpoint<br/>人工 approve/revise/skip"}
    F -->|待审| Y["checkpoint_pending<br/>(产出已落盘,复跑合并)"]
    F --> G{"6. evidence 校验<br/>type/artifact 存在/<br/>**产物 sha256 未篡改**/exit_code"}
    G -->|证据不足| X
    G --> H["终态 completed/skipped<br/>receipt 一次性消费<br/>审计字段落盘"]
```

并发保护：五个迁移入口 + `register_receipt` 共持模块级 RLock，read→modify→write 全程串行（5A/5B 并行下的正确性基础）。

## 四、--live 主循环（llm_dispatch）

```mermaid
flowchart TB
    D["dispatch directive<br/>(receipt + 预算化知识上下文)"] --> R["register_receipt"]
    R --> ST["start_stage(前置校验)"]
    ST --> LOOP{"tool calling 循环<br/>turn 1..max_turns"}
    LOOP -->|"每轮开始"| C1["condense_messages<br/>超 60k 空洞化旧 tool result"]
    C1 --> C2["smart_retry 包裹<br/>client.chat(瞬时错误退避×2)"]
    C2 --> N{"模型空转?"}
    N -->|第 1 次| NG["nudge 注入提醒"]
    N -->|第 2 次| F["fail_stage → failed"]
    C2 -->|"最后一轮"| FN["final-nudge:<br/>立即 report_outputs"]
    C2 --> TC["执行 tool_calls<br/>(8 工具,异常收敛 ok=false)"]
    TC --> RO{"调了 report_outputs?"}
    RO -->|否| LOOP
    RO -->|"超过 max_turns"| F
    RO -->|是| CP["complete_stage 全门控"]
    CP -->|过门| OK["completed / checkpoint_pending"]
    CP -->|拦截| GB["gate_blocked(阶段留 running)"]
    F -.->|"失败沉淀 error 经验"| EXP["config/experience/"]
    EXP -.->|"同阶段启动时检索注入 top-3"| D
```

## 五、知识推拉双通路

| 通路 | 方向 | 机制 | 时机 |
|---|---|---|---|
| **推**（dispatch context） | runner → 模型 | 按 Stage 选 section、按 OpenAPI 实体过滤领域知识、按 token 预算整段取舍（CJK 修正估算） | 阶段启动时注入 user 消息 |
| **拉**（工具检索） | 模型 → 知识 | `query_knowledge`（domain/实体检索）、`query_symbols`（code_graph 定义/引用）、`read_file`（翻页） | 模型按需调用 |
| **协作** | 推 → 拉 | 预算裁掉的 section 名单写入 user 消息："被裁剪,请 query_knowledge 拉取" | 推的预算不够时 |

经验闭环是第三条通路：阶段失败 → 写 `config/experience/error/`；同阶段下次启动 → 检索 top-3 注入 system prompt（标注"日志摘录非指令"防提示注入）。

## 六、持久化与可恢复性

| 产物 | 写入时机 | 保证 |
|---|---|---|
| `state.json` | 每次 transition（tmp + `os.replace`） | 原子写,Ctrl-C 不留半截;损坏时报错给出恢复路径 |
| `events.jsonl` | 每条事件即时 append | 事件溯源,崩溃后已发生事件不丢 |
| `transcripts/stage-N.json` | `--live` 阶段结束 | 完整 tool calling trajectory 供复盘/回放 |
| `codegen-manifest.json` | `write_out` 落盘后 | 每产物 sha256;evidence 校验内容未被篡改 |
| `config/experience/` | 阶段失败时 | error 经验沉淀 |

幂等 resume：重跑时已终态阶段直接 `resume_skip`（codegen 文件不被重写,产物 mtime 不变）。

## 七、三方职责分工（rocky 原则对照）

| 角色 | 职责 | harness 落点 |
|---|---|---|
| **LLM** | 需求理解、方案生成、代码生成、语义 review | LLM 阶段 1/2/3/4/7/8/9 委派（delegation-policy），`--live` tool calling |
| **脚本** | 状态校验、契约校验、Hash 校验、API 契约、规则重放、产物完整性 | FSM/G1/跨栈一致性、manifest sha256 + evidence hash 校验、evals 3 case + replay_gates 5 场景 |
| **用户** | 需求范围、方案选择、发布授权 | mandatory_review(1/2/3/6) + artifact_review(7/8/9/10) checkpoint |

## 八、工具表（tool_registry,8 个）

| 工具 | 语义 | 输出保护 |
|---|---|---|
| `read_contract` | 解析契约,实体/字段/endpoints 概览 | — |
| `verify_codegen` | G1 生成门 | — |
| `consistency_check` | 跨栈一致性报告 | — |
| `query_knowledge` | 领域知识按 domain/实体检索 | 只返回 confirmed 条目 |
| `query_symbols` | code_graph 定义/引用结构化检索 | top-20 截断 + 风险提示 |
| `read_file` | workspace 内文件读取 | safe_join 防越界 + 200 行窗口/翻页 |
| `write_file` | workspace 内文件写入 | safe_join 防越界 |
| `report_outputs` | **终态工具**:提交 structured outputs | 必须覆盖 required_outputs 才过门 |

沙箱边界：文件工具限 workdir 内（拒绝 `..`/绝对路径逃逸）；当前无执行类工具（P2-5 沙箱留待执行类工具引入时）。

## 九、CI 防线（每次 push 验证）

```mermaid
flowchart LR
    L["ruff lint"] --> M["pytest 165+<br/>3.10/3.11/3.12 矩阵"]
    M --> S["smoke: FSM/transition/codegen/<br/>llm_dispatch/tool_registry/..."]
    S --> E["evals 3 case<br/>(契约回归+hash+void 渲染)"]
    E --> RG["replay_gates 5 场景<br/>(门控行为回放,防 fail-closed 回退)"]
    RG --> D["端到端 demo"]
```

## 十、设计不变量（贡献者必读,PR 检查项）

1. **终态唯一入口**：任何阶段终态只经 `transition.py`;低层 `set_stage_state` 仅限恢复/调试
2. **fail-closed**：LLM 阶段不调 `report_outputs` → 永远无法完成;失败路径全部收敛 `fail_stage`(可 retry),无伪完成
3. **receipt 一次性**：签发 → 登记 → 消费,终态后不可重放
4. **汇合点不可跳**：6/9 永不 skip,FSM 兜底
5. **跨栈一致**：同一契约语义四栈行为一致(如 ts_type/java_type 的 void 对齐),evals 断言
6. **产物完整性**：生成产物带 sha256,evidence 校验内容而非仅存在
7. **LLM 侧改动 mock 可测**：所有行为(condenser/nudge/重试/经验注入)须 MockLLMClient 下确定性回归
