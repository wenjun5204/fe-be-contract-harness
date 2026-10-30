# Changelog

本项目所有显著变更记录于此文件。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Added
- **Stage 8 测试执行闭环(P0)**:阶段语义从"测试用例生成"扩为"生成与执行闭环"——
  执行(沙箱白名单)→ 失败诊断归因(LLM 委派)→ 修复(LLM 委派)→ 复验门,修复轮上限 3,
  耗尽即 `failed` 落盘,人工 retry 是唯一恢复入口;测试不绿到不了 Stage 9。
  - 新增 `lib/test_execution.py`:jest/vitest 摘要解析(只取 Tests 行语义)、失败用例提取、
    fail-closed 门控(无摘要/无用例/超时/非零退出均不放行)。
  - 新增 `run_tests` live 工具;新增 3 个 Agent:quality/test-executor(只执行不修)、
    test-failure-analyzer(归因 impl/case/env 三分类,不修代码)、test-fixer(按 diagnosis
    最小修复,生成区不手改)。
  - `resolve_subagents` 支持 dict 型阶段 `default` 键(无 stacks 时的缺省执行者)。
  - Stage 8 required_outputs 增至 `["test_cases", "test_report"]`——门控只认 test_report,
    不认用例表自述。
  - 环境边界:非 auto 非 live 仍签发 directive(不越权);live+auto mock 未覆盖时
    沿用降级 skip 语义;无 repo(演示)不硬造假报告。

### Added
- **React Native / Expo 全流程支持（第 5/6 栈）**：新增 `react_native` 与 `expo`（RN 的 Expo 托管工作流子类适配器）两个 StackAdapter，共享 React 的 OpenAPI→TS 映射，生成 `src/types/api.ts` + `src/api/client.ts`（fetch 请求层）。
  - 工程命令映射：LINT = `eslint src --ext .ts,.tsx` + `tsc --noEmit`，BUILD 门 = `tsc --noEmit`（类型检查，真机 metro bundle / EAS 构建归 CI），TEST/COVERAGE = jest；部署路由 `app-bundle` / `eas-build`（仅登记）。
  - 工程识别：裸 RN 以 `ios/Podfile` / `android/app` / `metro.config.js` 为标记，Expo 以 `app.config.{js,ts}` 独有标记识别。
  - 全链路接线：runner 5B 前端波、`repo_knowledge.detect_stack`、跨栈一致性默认栈集、`tool_registry` 的 `verify_codegen`/`run_check` stack enum、`delegation-policy.json` 5B.by_stack → 新增 `codegen/rn-codegen` Agent（含 agent.json/prompt.md）。
  - 评测集与测试同步扩展至六栈（test_codegen/test_consistency/test_delegation/test_repo_knowledge/test_runner/evals），demo 脚本六栈生成演示。

### Fixed
- **react 栈工程识别误判**：MARKERS 中的 `src/App.tsx` 与 RN TS 工程同名文件冲突，会把 RN 项目误判为 React Web；收紧为 `vite.config.ts` 单标记（vite 为 Web 独有）。

## [0.2.0] - 2026-10-23

### Added
- **观测体系（O1/O2）**：stage timing（`started_at`/`checkpoint_pending_at` 落盘，终态计算 `execution_seconds`——**剔除人工审批等待**，`checkpoint_wait_seconds` 单列）；`summary()` 输出 `stage_durations`；`runner report` 子命令聚合 events.jsonl + state.json 输出阶段耗时/慢点/门控拦截/LLM 行为指标。
- **KPI 可量化收益**：`report` 输出六项指标——success_rate、failure_events/recovered_stages、human_interventions、total_duration_seconds、requirement_scale（`contract_stats` 落 state，重跑不覆盖首次口径）、throughput；每次 report 追加 `metrics.jsonl` 形成跨 run 基线。
- **双循环设计落档**：ARCHITECTURE.md 新增内循环（阶段内自纠错，已成型）/外循环（三条回流管）章节 + E1 评测采集管道——`--live` 失败 transcript 自动落盘 `evals/regressions/.pending/`，人工筛选后浓缩为回归场景。
- **工程化设计架构文档**：`docs/ARCHITECTURE.md`（分层/门控链/--live 主循环/双循环/三方分工/设计不变量，mermaid）。
- **英文完整文档**：`docs/README.en.md`；README 加 CI/License/Python badge。

### Fixed
- **--auto 模式 checkpoint 审计字段错误**：确定性阶段显式传 checkpoint decision 时 `approved_by` 被误标 `user`（自动批准记成人工批准，KPI 人工介入数虚报）；三处调用点补 `auto_approve` 使其如实。

## [0.1.1] - 2026-10-22

对标成熟 agent harness（OpenHands/SWE-agent/LangGraph/Claude Code）的系统性改造，
详见 [HARNESS_UPGRADE.md](HARNESS_UPGRADE.md)。

### Added - 基础可靠性（P0）
- state.json 原子写（tmp + rename），Ctrl-C 不留半截文件；读取容损坏并给出恢复路径。
- LLM 阶段失败经 `fail_stage` 真实落 `failed`（此前永远卡 running），人工 `retry` 有合法入口。
- `smart_retry` 接线 LLM 调用：瞬时错误（超时/429/5xx）退避重试，永久错误零重试。
- 事件溯源：每条事件即时 append `events.jsonl`；`--live` transcript 落盘 `transcripts/`。
- 幂等重跑：已终态 codegen 阶段 `resume_skip`，不再"文件先重写再被门控拦"。
- coverage_collector 接线 5A/5B（此前 outputs 硬编码字符串）。
- planner 接线替换硬编码 SKIP_STAGES（路径决策数据驱动）。

### Added - 执行层（P1）
- `query_symbols` 工具（code_graph 结构化检索，top-20 截断）；`read_file` 加翻页/200 行截断（ACI 紧凑化）。
- max_turns 最后一轮 final-nudge 收束提示；失败沉淀 error 经验。
- 知识推拉协作：预算裁掉的 section 提示模型用 `query_knowledge` 按需拉取。
- 经验闭环合龙：同阶段历史失败教训注入 system prompt top-3（标注"日志摘录非指令"防注入）。
- 确定性 condenser：messages 超 60k 字符空洞化旧 tool result（wire 格式不破，transcript 全量保留）。
- self_heal 启动自检（critical 缺失 fail-fast）；**收掉 auto_install 的 shell=True 路径**（开源安全）。
- parallel_wave_scheduler 接线 5A/5B 同波并行；transition 五入口 + register_receipt 加 RLock（修复并行下 receipt 登记被覆盖的并发 bug）。

### Added - 确定性防线（P2）
- **产物 Hash 校验**：codegen-manifest 记录产物 sha256，evidence 强校验内容未被篡改（旧 manifest 降级放行）。
- **评测集扩充**：1 → 3 case（binary-ping 空响应回归 / ref-enum-array $ref+enum+嵌套 array+跨栈一致性）。
- **门控行为回放**：`evals/replay_gates.py` 五场景 mock 确定性重放（正常交付/空转 failed/缺产出 gate_blocked/瞬时错误重试/前置 blocked），接进 CI 防止 fail-closed 语义回退。

### Fixed
- `java_type(None)` TypeError：无 2xx JSON 响应端点（二进制回图/204）导致 Java 栈生成崩溃，补 `void` 兜底与 `ts_type(None)->void` 对齐，附四栈回归测试。
- token 估算 CJK 修正：`len//2` 对中文低估约一半（4000 预算实际注入近翻倍内容）→ ASCII 1/4 + CJK 每字 1。

### Security
- self_heal 不再自动执行安装命令（shell=True 移除），改为 fail-fast 报告 + 可行动建议。

## [0.1.0] - 2026-10-10

首个发布：**确定性流程内核 + Agent 协作协议**。

### Added
- OpenAPI 3.x 契约解析（YAML/JSON；基础类型/object/array/enum/$ref）。
- 四栈代码生成（React / Vue / Node / Java 骨架），同一契约派生。
- 三重质量门：G1 生成门、跨栈一致性、生成产物漂移检测、运行时契约校验（live check）。
- 12 阶段状态机：FSM + 前置就绪 + required_outputs + receipt（一次性消费）+ checkpoint（人工卡点）+ evidence 全门控；`transition.py` 唯一终态入口。
- LLM 委派协议：dispatch directive + receipt + 按 Stage/实体/token 预算的自动知识上下文。
- `--live` 模式：LLM 阶段经 tool calling 主循环真实执行（mock / openai 兼容运行时），全程走 transition 门控无旁路。
- 两类知识库：领域知识（跨项目业务规则，confirmed/assumption/deprecated 状态机，AI 推断不可直接进 confirmed）与仓库知识（目标仓库 `.agents/`）。
- 开源合规：LICENSE(MIT) / CONTRIBUTING / SECURITY / issue 与 PR 模板。
- CI：ruff lint + Python 3.10/3.11/3.12 矩阵 + 全量确定性自测 + evals + 端到端 demo。

---

[Unreleased]: https://github.com/wenjun5204/fe-be-contract-harness/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/wenjun5204/fe-be-contract-harness/compare/v0.1.0...v0.2.0
[0.1.1]: https://github.com/wenjun5204/fe-be-contract-harness/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/wenjun5204/fe-be-contract-harness/releases/tag/v0.1.0
