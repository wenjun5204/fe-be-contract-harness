# 技术方案：领域知识库作用域隔离（目录即作用域）

> 状态：v1.0 已定稿（方案 B）
> 作者：liuwenjun05 + Claude Code ｜ 日期：2026-11-09
> 来源：大契约压测（Stripe 612 端点）+ yivote P2-2 验证两次真实撞到的知识泄漏问题
> 待办映射：HARNESS_UPGRADE.md「下一步候选」第 5 条遗留项

---

## 1. 背景与根因

### 1.1 两次真实撞到同一问题

- **yivote P2-2 验证（2026-11-06）**：真实子 Agent 执行 Stage 1 时，dispatch context 注入了
  「全家福·接福气」的领域知识（福值规则、门牌等级），子 Agent 不得不显式声明
  "不作为本产品事实来源"并记入 spec assumptions；
- **Stripe 大契约压测（2026-11-09）**：1538 个完全陌生的实体场景下，business-knowledge
  section 仍然注入全家福知识，浪费预算且有误导面。

### 1.2 根因链（逐条在代码验证）

| # | 位置 | 问题 |
|---|---|---|
| 1 | `lib/context_orchestrator.py` `_matches_entity` | `type == "convention"` 的条目**恒注入**——本意为跨实体工程约定，但 family-blessing.md 的业务规则也打了 convention 标签 → 任何契约都注入全家福。**泄漏主通道**，与实体匹配无关 |
| 2 | `lib/domain_knowledge.py` `load_entries` | KB 是单一全局池（`config/domain-knowledge/<domain>/`），没有产品维度；所有项目读同一个池 |
| 3 | `_matches_entity` 实体匹配 | 子串 contains——stripe 的 `order_return` 命中 entity `Order`（双向误报） |
| 4 | E2 写侧 | drift 回流 `write_entry` 写入同一全局池——每跑一个真实项目都会加重污染。当前 4 个条目没爆发只因跑的项目少 |

### 1.3 结构性判断

这不是逐 bug 修复的事。外循环「知识库越跑越聪明」的前提是隔离——否则**知识越丰富、
污染面越大**，最终 dispatch context 里全是不相干产品的事实，预算被无效知识占据。

---

## 2. 设计目标与红线

1. 项目 A 的业务知识**绝不**进入项目 B 的 dispatch context；
2. 跨项目工程约定（错误码规范、分页风格）**继续全局共享**（KB 本意）；
3. 零配置冷启动可用（新契约不先登记产品也能跑）；
4. E2 写侧同步归位，不落全局；
5. **确定性可测**——匹配链不引入任何 LLM 判断（三方分工中这是「脚本」职责）。

对齐仓库三条设计红线：终态唯一入口（本方案不涉）、fail-closed（写侧缺 product 不落
全局）、mock 可测（目录过滤纯文件系统操作，确定性）。

---

## 3. 方案：目录即作用域（B 方案）

### 3.1 方案选型

作用域信息（"这条知识属于哪个产品"）的两种承载：

| 维度 | A：frontmatter `product` 字段 | **B：目录位置（选定）** |
|---|---|---|
| 泄漏面可审计 | 需逐条解析才知道归属 | `ls products/` 一眼看清；`find` 即孤儿检测 |
| 隔离强度 | 字段缺失时的缺省值是两难（当全局→重现泄漏；当孤儿→真知识静默失效） | 位置即真相：不在当前产品目录的文件**物理上不读取**，无缺省值问题 |
| E2 写侧归位 | 填错字段即静默污染 | 写错路径即显式错位 |
| 迁移成本 | 低（加字段） | 中（挪文件 + load_entries 加 root 维度） |

**选定 B**：迁移成本一次性，结构可靠性永久；且避免与 `type=convention` 恒注入
同类的"缺省值陷阱"。A 的低迁移成本对 4 个条目的现状收益太小。

### 3.2 目录布局

```
config/domain-knowledge/
├── _global/                        # 真正跨项目的工程约定
│   ├── backend-api-conventions.md
│   ├── frontend-conventions.md
│   └── qa-conventions.md
└── products/
    ├── fe-backend-mini/            # 全家福·接福气
    │   └── business/family-blessing.md
    ├── yivote/                     # 目前为空——正确:无知识不该注入别人的
    └── stripe/
```

- `_global/` 下的 domain 子结构（business/backend/frontend/qa）保持现状语义；
- 旧路径 `config/domain-knowledge/<domain>/` **迁移后删除**，不留双读
  （双读会让"忘迁移的条目静默失效"，又一个缺省值陷阱；迁移脚本一次清零）；
- frontmatter 保留 `entity`/`type`/`status` 等字段，做产品内的实体过滤。

### 3.3 product_id 解析链（run 启动时确定，三级优先）

1. **显式 `--product <id>`**：人工命名（推荐真实项目都用这个，语义最清晰）；
2. **契约派生**：`info.title` 规范化为 slug（"咦投票 API" → `yivote-api`）——零配置冷启动；
3. **state.json 固化**：首次解析的 product_id 写入 state，重跑沿用（同产品改 title 不换 scope）。

product_id 规范化规则：小写、非字母数字转 `-`、截断 64 字符；与目录名严格一致。

### 3.4 注入语义表

| 条目位置 | 注入条件 |
|---|---|
| `_global/` | 所有 run；`type=convention` 恒注入规则**仅在这一层保留**（从"全局行为"收窄为"global 层行为"） |
| `products/<pid>/` | `run.product_id == pid` 才加载；加载后仍做实体过滤 |
| 实体匹配 | **精确集合交集**：entry 声明 `entities: [Order, OrderItem]`，与契约实体名精确比对；替换子串 contains |

### 3.5 写侧（E2 drift 回流 + E3 确认）

- drift 检出的 assumption 条目写入 `products/<pid>/`（用当次 run 的 product_id）；
- product_id 无法解析（极端冷启动）→ 写入 `pending/` 并附 warning，**绝不落 `_global/`**；
- E3 `confirm_entry` 人工升级时可将条目迁至 `_global/`——跨产品通用是**显式人工决策**
  （对齐"脚本采集、人筛选"红线）；
- `query_knowledge` 工具（LLM 拉取侧）同步按当前 run 的 product 过滤，只返回
  confirmed 条目的语义不变。

### 3.6 现有条目迁移

| 条目 | 归宿 | 说明 |
|---|---|---|
| backend/frontend/qa `conventions.md` ×3 | `_global/` | 确为跨项目工程约定（错误码规范等），放对了 |
| `business/family-blessing.md` | `products/fe-backend-mini/business/` | fe_backend_mini 产品的业务规则 |
| `business/order.md` | `products/fe-backend-mini/business/` | 归属 fe_backend_mini 订单域（订单核心生命周期是全家福项目的订单实现） |

迁移以一次性脚本执行 + evals/replay 断言不回归；迁移后旧目录删除（3.2）。

---

## 4. 明确不做的事（边界）

- **多产品 monorepo 契约**（一个契约横跨多产品）：MVP 不处理，声明边界；
- **实体模糊/语义匹配**（embedding 检索）：不进匹配链，确定性优先；
- **KB 权限/多租户**：单机单用户场景无此需求；
- **双读兼容期**：不留旧路径回退（3.2 已述）。

---

## 5. 验收标准

1. stripe run 的 dispatch context **不含** FamilyBlessing/福值条目（当前实测含）；
2. yivote run 的 business-knowledge 为**空**（无 yivote 知识是事实，不该拿全家福凑数）；
3. petstore 回归：注入内容不变（仅 `_global/` conventions）；
4. 全量 pytest + replay_gates + 三契约（petstore/yivote/stripe）e2e 复跑不回归；
5. 孤儿检测：一条命令可列出 `products/` 下与任何已知 product_id 无对应的条目；
6. E2 回流写侧：yivote run 触发的 drift 写入 `products/yivote/`（而非全局）。

---

## 6. 实施拆分

| 步骤 | 内容 | 触及文件 |
|---|---|---|
| 1 | product_id 解析链 + state 固化 | `lib/runner.py`、`lib/state_manager.py` |
| 2 | 目录布局 + 读侧过滤（_global ∪ products/<pid>） | `lib/domain_knowledge.py`、`lib/context_orchestrator.py` |
| 3 | 实体精确匹配替换子串 | `lib/context_orchestrator.py` |
| 4 | E2 写侧归位 + pending 兜底 | `lib/domain_knowledge.py`、drift 回流调用点 |
| 5 | 现有 4 条目迁移脚本 + 执行 | `config/domain-knowledge/` |
| 6 | 回归测试（三 fixture 断言 + replay + e2e 复跑）+ 文档同步 | `tests/`、`HARNESS_UPGRADE.md` |

预估总量：集中在 domain_knowledge / context_orchestrator / runner 三个文件，
测试以 fixture 目录 + 断言为主。
