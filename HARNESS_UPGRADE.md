# Harness 改造记录 —— 对标成熟 Agent Harness 的优化路线

> 起点：v0.1.0 开源后的全库审计（2026-10）。本文档记录核心思想、执行步骤与进度，供后续追踪。
> 配套计划文件：P2 未完成项见文末「进度追踪」。

---

## 一、改造的核心思想

### 1. 全库审计的关键发现

审计发现项目最大的问题不是缺能力，而是**能力已写好但没有接线**——大量模块有完整实现和测试，却从未进入执行主链：

| 孤儿模块（改造前状态） | 说明 |
|---|---|
| `transition.fail_stage` / `retry_stage` | 写好且过测，但全库无人调用——LLM 阶段失败永远卡在 `running` |
| `smart_retry` | 指数退避写好了，`llm_client` 调用却一次失败即弃 |
| `self_heal` / `experience` / `code_graph` / `coverage_collector` / `planner` | 只有自测，主链不用；runner 用硬编码 `SKIP_STAGES` 和顺序循环 |
| `parallel_wave_scheduler` | 就绪可用，5A/5B 却顺序执行 |

结论：**最大杠杆是"接线"而非"新写"**。

### 2. 对标的成熟框架机制

| 本项目 | OpenHands | SWE-agent | LangGraph | Claude Code |
|---|---|---|---|---|
| events.jsonl 事件落盘 | 事件溯源（一切皆 event，可回放） | trajectory 保存 | — | — |
| fail_stage 失败落盘 | ErrorEvent 一等公民 | — | 节点 error state | — |
| smart_retry 瞬时重试 | provider 错误分类重试 | — | — | API 退避 |
| 确定性 condenser | condenser（LLM 摘要版） | history processors | — | compact |
| final-nudge 收束 | LLMSummarizingError 兜底 | — | — | 最后机会输出 |
| 知识推拉协作 | microagents | — | — | 摘要+工具拉取 |
| query_symbols 紧凑输出 | — | **ACI 设计原则** | — | — |
| 幂等 resume | AgentState 恢复 | — | **checkpointer** | — |
| transition RLock | — | — | 并行分支 + 汇合 | — |

### 3. 三条设计红线（所有改造不得违反）

1. **终态唯一入口**：所有终态只经 `transition.complete/skip/fail`。改造只允许动三类东西——LLM 的输入（压缩/注入）、调用次数（重试/nudge）、旁路记录（事件/经验）。绝不新增绕过门控的路径。
2. **fail-closed**：每个失败路径（重试耗尽、max_turns、压缩后不收敛）最终收敛到 `fail_stage`，无"伪完成"。模型只能通过工具影响世界，必须 `report_outputs` 提交 structured outputs 才能过门。
3. **mock 可测性**：所有 LLM 侧行为改动必须在 `MockLLMClient` 下可确定性测试（对应成熟 harness 的 trajectory 回归）。

### 4. 改造方法论

```
审计(找孤儿模块和真实缺口) → 按性价比排序(P0 纯接线 > P1 需设计 > P2 需外部条件)
→ 每项:接线 + 回归测试 + 全量验证 → 分逻辑提交
```

---

## 二、改造步骤

### P0 —— 纯接线+小修（✅ 已全部完成，commit 94ae3a8 / 2353bf5 / ecabe2e）

| # | 改动 | 文件 | 状态 |
|---|---|---|---|
| P0-1 | state.json 原子写：tmp + `os.replace`，read_state 容损坏给恢复路径 | `lib/state_manager.py` | ✅ |
| P0-3 | llm_dispatch 失败接 `fail_stage`：失败真实落 failed，可人工 retry | `lib/llm_dispatch.py` | ✅ |
| P0-4 | `smart_retry` 包 client.chat：瞬时错误（timeout/429/5xx）退避重试 2 次，永久错误零重试 | `lib/llm_dispatch.py` | ✅ |
| P0-5 | 事件溯源：每条事件即时 append `events.jsonl`；--live transcript 落盘 `transcripts/stage-N.json` | `lib/runner.py` | ✅ |
| P0-2 | 幂等重跑：5A/5B 终态先查后跳（`resume_skip`），已完成的 codegen 不再先重写再被拦 | `lib/runner.py` | ✅ |
| P0-6 | coverage_collector 接线 5A/5B：有目标仓库时采集真实覆盖率，失败降级字符串 | `lib/runner.py` | ✅ |
| P0-7 | token 估算 CJK 修正：`len//2` 对中文低估一半 → ASCII 1/4 + CJK 每字 1 | `lib/context_orchestrator.py` | ✅ |
| P0-8 | planner 接线替换硬编码 SKIP_STAGES：路径决策来自数据源，理由标"planner 确认" | `lib/runner.py` | ✅ |

**P0 完成后达到的底座**：崩溃安全 + 可续跑 + 失败可重试 + 全程可回放——成熟 harness 的共同底座。

### P1 —— 需设计的接线（✅ 已全部完成，commit 5c67ccd / 3096ea9 / 04911b1）

| # | 改动 | 文件 | 状态 |
|---|---|---|---|
| P1-4 | code_graph → `query_symbols` 工具（定义/引用、top-20 截断）；read_file 加 offset/limit + 200 行截断 | `lib/tool_registry.py` | ✅ |
| P1-2 | max_turns 最后一轮 final-nudge（交作业出口）；失败沉淀 error 经验（闭环写侧） | `lib/llm_dispatch.py` | ✅ |
| P1-3 | 预算裁掉的 section 在 user 消息提示用 query_knowledge 按需拉取（推拉协作） | `lib/llm_dispatch.py` | ✅ |
| P1-5 | 经验闭环读侧：同阶段历史失败教训注入 system prompt top-3（标注"日志摘录非指令"防注入）——写读合龙 | `lib/llm_dispatch.py` | ✅ |
| P1-1 | 确定性 condenser：messages 超 60k 字符时空洞化较早 tool result（头部 500 字+重读提示），最近 3 条与 assistant tool_calls 不动（wire 格式成对）；transcript 落盘仍全量 | `lib/llm_dispatch.py` | ✅ |
| P1-7 | self_heal 接线 runner 启动（critical 缺失 fail-fast 给安装命令）；**收掉 auto_install 的 shell=True 路径**（开源安全） | `lib/self_heal.py` `lib/runner.py` | ✅ |
| P1-6 | parallel_wave_scheduler 接线 5A/5B 同波并行；transition 五入口 + register_receipt 加模块级 RLock（read-modify-write 全程串行） | `lib/runner.py` `lib/transition.py` `lib/delegation.py` | ✅ |

**P1 执行中发现并修复的真实并发 bug**：5A/5B 并行首跑出现"receipt 未登记"——两线程同时 read-modify-write state.json 互相覆盖。根因是 `register_receipt` 走 delegation 不经 transition 锁；将其纳入同一把锁后 12/12 全终态、零 blocked。这正是计划预判的并发风险点。

### P2 —— 可选/长期（⏳ 待做，依赖外部条件或真实用户反馈）

| # | 改动 | 前置条件 | 状态 |
|---|---|---|---|
| P2-1 | condenser LLM 摘要版（被空洞化轮次摘要成 recap） | P1-1 确定性版实测不够用 | ⏳ |
| P2-2 | platform/event_adapter 精确映射 + 各平台 fixture 测试 | 需真实平台（Claude Code/OpenClaw）运行时逐个验证 | ⏳ |
| P2-3 | trajectory 驱动 evals 回放：mock 重放断言门控行为不变（gate regression） | P0-5 已落盘，可直接开工 | ⏳ |
| P2-4 | coverage_gate 强拦接 checkpoint（低于阈值 → checkpoint_pending 而非 fail） | P0-6 真实覆盖率数据稳定后校准阈值 | ⏳ |
| P2-5 | 工具执行沙箱（若未来引入执行类工具） | 当前 7+1 工具无执行能力，暂不需要 | ⏳ |

---

## 三、架构改造前后对比

```text
改造前:
runner ──顺序循环──► transition(门控) ──► state.json(非原子写)
   │  硬编码 SKIP_STAGES                 失败卡 running,无 retry 入口
   └─ LLM 调用:一次失败即弃;全量历史累积无压缩;8 个辅助模块无调用方

改造后:
runner ──波次调度(5A/5B 并行)──► transition(RLock 串行) ──► state.json(原子写)
   │  planner 数据驱动 skip 决策             失败→failed 落盘→retry 入口
   │  启动 self_heal 自检
   └─ llm_dispatch 主循环:
        ├─ smart_retry 瞬时错误退避
        ├─ condenser 超 60k 空洞化旧 tool result
        ├─ final-nudge 最后一轮收束
        ├─ 知识推拉(context 推 + query_knowledge 拉 + query_symbols 结构化检索)
        ├─ 经验闭环(失败写入 → 同阶段检索注入)
        └─ 失败 → fail_stage + error 经验沉淀
旁路: events.jsonl(事件溯源) + transcripts/(trajectory) + config/experience/(经验)
```

## 四、进度追踪

**已完成**：
- ✅ P0 全部 8 项（2026-10-22，commit 94ae3a8 / 2353bf5 / ecabe2e）
- ✅ P1 全部 7 项（2026-10-22，commit 5c67ccd / 3096ea9 / 04911b1）
- ✅ 审计孤儿模块清零：smart_retry / self_heal / experience / code_graph / coverage_collector / planner / parallel_wave_scheduler / fail_stage / retry_stage 全部接入执行主链
- ✅ 测试从 139 → 162 个；ruff + pytest + smoke + demo 全绿

**验证命令**（每项改造后必跑）：

```bash
ruff check lib tests
python3 -m pytest tests/ -q
npm test
npm run demo
```

**下一步候选**（按建议优先级）：
1. P2-3 evals 回放——前置已齐（P0-5 落盘），防未来改动破坏 fail-closed 语义，性价比最高
2. 推送 + 合并 feature 分支回 main
3. P2-2 平台适配（等真实平台接入需求时逐平台 PR）
4. P2-1 / P2-4（等真实用户反馈）
