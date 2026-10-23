# 贡献指南

感谢你关注 fe-be-contract-harness！欢迎 Issue、PR 和讨论。

## 开发环境

- Python 3.10+（CI 在 3.10 / 3.11 / 3.12 上验证）
- Node.js 18+（用于 `npm` 脚本；核心逻辑是 Python）

```bash
git clone https://github.com/wenjun5204/fe-be-contract-harness.git
cd fe-be-contract-harness
pip install -r requirements.txt
```

## 提交 PR 前必做

```bash
ruff check lib tests    # lint,CI 同款基线(配置见 pyproject.toml)
npm test                # 全量确定性冒烟测试
python3 -m pytest tests/ -q
npm run demo            # 端到端演示
```

CI 会执行同样的检查（lint + 3.10/3.11/3.12 矩阵测试），全绿才会合并。

## 项目约定

### 状态迁移唯一入口

**不要直接写 `state.json`。** 所有阶段终态必须经 `lib/transition.py`（FSM 合法性、前置就绪、required_outputs、receipt、checkpoint、evidence 全门控）。`lib/state_manager.py` 的低层写能力仅用于恢复/调试。

### LLM 阶段不伪造完成

LLM 委派阶段在没有真实产出（`report_outputs` 提交 structured outputs）时必须停在 `running`，不得绕过门控标记 completed。新增旁路 = PR 会被拒。

### 生成器与契约对齐

修改四栈生成器（`lib/stack/`）时：

1. 确认 `evals/` 评测集仍通过；
2. 更新对应栈的 `tests/test_stack_adapter.py` / `tests/test_codegen.py` 断言；
3. `lib/contract/cli.py verify`（G1 生成门）和跨栈一致性不可回退。

### 知识库条目格式

`config/domain-knowledge/` 的条目带 JSON frontmatter（`id` / `domain` / `entity` / `type` / `status` / `source`）。AI 推断内容只能标 `assumption`，人工确认后才可 `confirmed`。提交前用 `python3 lib/domain_knowledge.py validate <文件>` 校验。

### 文档

代码注释和文档使用中文；新公共命令请在 `README.md` 补充用法。lint 配置豁免 E501 行宽（中文注释按 codepoint 计数不公平），但新代码尽量 ≤110 列。

## 提交信息格式

沿用现有风格：`type(scope): 摘要`，如：

```
fix(ci): 补 requirements.txt 修复 pip cache 失败
feat: --live 模式——LLM 阶段经 tool calling 主循环真实执行
docs(readme): 补 --live 模式说明
```

常用 type：`feat` / `fix` / `docs` / `refactor` / `test` / `chore`。

## Changelog

用户可感知的变更（新能力 / 行为变化 / 修复）请在 [CHANGELOG.md](CHANGELOG.md) 的
`Unreleased` 对应小节（Added/Changed/Fixed/Security）补一行，发版时合并为版本号段落。
纯内部重构、测试补充可不记。

## 报 Bug

开 Issue 时请附：

1. 复现命令（完整 CLI 调用）；
2. Python 版本；
3. 期望行为 vs 实际行为；
4. 相关日志或 `state.json` 片段（脱敏后）。

## 安全问题

不要在 Issue 里报安全问题，参见 [SECURITY.md](SECURITY.md)。
