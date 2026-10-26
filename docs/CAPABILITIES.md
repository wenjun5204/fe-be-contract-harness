# Harness 能力地图（必要能力清单与完成度）

> 用途：① 定义"一个合格的 agent harness 该有什么"的标准；② 标注当前完成度，作为后续迭代的 backlog。
> 图例：✅ 已过硬（可当卖点）/ ⚠️ 半成品（零件在、待接线）/ ❌ 缺口（需要时再做）
> 维护约定：每完成一项能力就更新对应行；新增能力先入表再动手。
> 配套：架构细节见 [ARCHITECTURE.md](ARCHITECTURE.md)；改造历史见 [HARNESS_UPGRADE.md](HARNESS_UPGRADE.md)。

---

## 第 1 层：状态与流程（地基）

| 能力 | 说明 | 完成度 | 落点 |
|---|---|---|---|
| 状态机 + 唯一迁移入口 | 阶段推进必须经统一门控,不允许旁路写 | ✅ | `lib/transition.py`(六道门) |
| 可持久化 + 断点恢复 | 崩溃/中断后从上次进度续跑 | ✅ | 原子写 + `resume_skip` 幂等 |
| 失败是一等公民 | 失败真实落状态、可重试,不卡死不伪装 | ✅ | `fail_stage`/`retry_stage` |
| 工作流定义与执行解耦 | DAG/FSM 是数据,换流程不改代码 | ✅ | `build_execution_plan` Kahn 分层驱动主循环;parallel_groups 校验;7/8 波次并行生效 |

## 第 2 层：信任与门控（差异化核心）

| 能力 | 说明 | 完成度 | 落点 |
|---|---|---|---|
| 委派凭据防伪 | 产出绑定不可伪造、不可重放的凭据 | ✅ | receipt 登记/一次性消费/防重放 |
| 产出校验 | required_outputs 机验 + 语义校验 | ✅ | FSM required_outputs + Stage 9 六项机验 |
| 证据链 | 完成凭 exit_code/hash/artifact,不凭嘴 | ✅ | `_validate_evidence` |
| 人工卡点 | 高风险节点人拍板 approve/revise/skip | ✅ | mandatory/artifact 两类 checkpoint |
| 产物完整性追踪 | 产物从生到交不被静默篡改 | ✅ | manifest sha256 + evidence hash 校验 |

## 第 3 层：执行环境（Agent 干活的场地）

| 能力 | 说明 | 完成度 | 落点 |
|---|---|---|---|
| 工具注册表 + 参数校验 | 工具是显式清单,不是任意 shell | ✅ | `tool_registry`(8 工具 + schema 校验) |
| 工具沙箱边界 | 读写限制工作区内,防越界 | ⚠️ | read/write_file 有 `safe_join`;`verify_codegen`/`read_contract` 的 path 参数未校验 |
| 执行类工具隔离 | 跑测试/构建需白名单+超时+输出截断 | ❌ | 当前 8 工具全是读/检索类;引入执行类前必须先做(P2-5) |
| ACI 输出纪律 | 工具输出紧凑、错误信息可行动 | ✅ | read_file 翻页/截断、query_symbols top-20 |

## 第 4 层：LLM 交互（内循环）

| 能力 | 说明 | 完成度 | 落点 |
|---|---|---|---|
| tool calling 主循环 | 模型只能经工具影响世界 | ✅ | `llm_dispatch` |
| 自纠错机制 | 工具错误回传可行动信息 | ✅ | `ok=false` 收敛回模型 |
| 轮次/预算上限 | 防失控,耗尽即 fail | ✅ | max_turns + final-nudge |
| 上下文管理 | 长对话不失忆 | ✅ | 确定性 condenser(LLM 摘要版留储备,P2-1) |
| 瞬时错误容错 | 429/超时重试,永久错误 fail-fast | ✅ | `smart_retry` |
| 结构化产出契约 | 交付必须结构化,不接受自由文本 | ✅ | `report_outputs` + Stage 1 SDD 机验 |

## 第 5 层：知识与上下文供给

| 能力 | 说明 | 完成度 | 落点 |
|---|---|---|---|
| 领域知识注入 | 按阶段/实体推送业务规则 | ✅ | dispatch context(推) |
| 按需检索 | Agent 主动查,而非全量塞 | ✅ | query_knowledge/query_symbols(拉)+ 裁剪提示(协作) |
| 知识可信度分级 | AI 推断不污染已确认层 | ✅ | assumption/confirmed 状态机,写侧校验拦截 |
| 知识回流 | run 中学到的写回知识库,越用越厚 | ⚠️ | 管道零件齐(`write_entry` 零调用方),即外循环 E2/E3 |
| 仓库上下文 | 目标仓库技术栈/约定 | ✅ | `repo_knowledge` |

## 第 6 层：观测与可审计

| 能力 | 说明 | 完成度 | 落点 |
|---|---|---|---|
| 事件溯源 | 一切动作落日志,可回放 | ✅ | `events.jsonl` |
| 轨迹保存 | LLM 完整对话可复盘 | ✅ | `transcripts/` |
| 阶段计时 | 哪里慢看得见 | ✅ | O1(审批等待单列) |
| KPI 指标 | 成功率/人工介入/吞吐可量化 | ✅ | O2 六指标 + `metrics.jsonl` |
| 跨 run 对比 | 和上次比好没好 | ⚠️ | metrics 在积累,趋势消费端待数据 |

## 第 7 层：回归防线（不变量的守卫）

| 能力 | 说明 | 完成度 | 落点 |
|---|---|---|---|
| 行为回放评测 | 门控语义改动被 CI 抓住 | ✅ | `replay_gates` 5 场景 |
| 契约回归评测 | 生成器改动不破坏产物 | ✅ | `evals` 3 case |
| 真实失败回流 | 生产新失败自动变回归素材 | ⚠️ | E1 采集已通,人筛选待真实数据 |
| lint/类型/多版本矩阵 | 代码质量底线 | ✅ | ruff + Python 3.10-3.12 矩阵 |

## 第 8 层：分发与接入（用户视角）

| 能力 | 说明 | 完成度 | 落点 |
|---|---|---|---|
| 一键安装 | clone 后 pip install 能跑;进阶为发版到包管理器 | ⚠️ | clone+requirements 可跑;PyPI 未发(资源路径需改 `importlib.resources`) |
| 平台适配 | 真实平台能挂载 | ⚠️ | hooks 已有,`event_adapter` 映射未在真实平台验证(P2-2) |
| 端到端演示 | 5 分钟体验 | ✅ | `npm run demo` |
| 文档完备 | README/架构/贡献/安全 | ✅ | 全齐(含 CHANGELOG/ARCHITECTURE/CAPABILITIES) |

---

## 总览：按完备度排序

```text
已过硬(可当卖点):   状态门控层(含 DAG 驱动编排)、信任链、LLM 内循环、观测体系、回归防线
半成品(零件在待接线): 工具沙箱全覆盖、知识回流、跨run对比、平台验证、PyPI
缺口(需要时再做):     执行类工具+沙箱(P2-5)、LLM 摘要 condenser(P2-1)
```

**两个战略观察**：

1. **强项恰是别家弱项,弱项恰是别家强项**——门控/信任链是差异化,执行工具/平台生态是生态位劣势。继续深挖门控侧比补齐执行侧更符合项目定位。
2. **"半成品"的共性是零件都在、只差接线**(与 2026-10 审计发现一致)——接一根线就多一项能力,成本低。本清单可直接当 backlog 用。
