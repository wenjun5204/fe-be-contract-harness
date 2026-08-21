# 安装 fe-be-contract-harness

以 OpenAPI 契约为唯一事实源的前后端契约驱动 SDLC 插件。支持 CatPaw / CatClaw / Claude Code / Codex / OpenClaw / OpenCode。

## 前置依赖

- Python 3.8+(解析 / 生成 / 门控脚本运行时)
- Node.js 18+(可选,前端栈构建)
- `pyyaml`(YAML 契约解析):`pip3 install pyyaml`

## 快速安装

```bash
# 克隆仓库
git clone https://github.com/wenjun5204/fe-be-contract-harness.git ~/.fe-be-contract-harness

# 依赖检查
python3 ~/.fe-be-contract-harness/hooks/dep-guard

# 冒烟自测(可选,确认确定性内核可用)
cd ~/.fe-be-contract-harness && npm test
```

## 两种使用方式

### 方式 A:作为确定性 CLI 工具(现在即可用)

```bash
cd ~/.fe-be-contract-harness

# 从契约生成代码骨架
python3 lib/contract/cli.py generate contract.yaml --stack node --out gen/node

# G1 生成门 / 跨栈一致性 / 漂移检测
python3 lib/contract/cli.py verify contract.yaml --stack node
python3 lib/contract/cli.py check contract.yaml
python3 lib/contract/cli.py drift contract.yaml --stack node --gen-dir gen/node

# 编排 runner(确定性阶段真实执行,LLM 阶段签发委派指令)
python3 lib/runner.py run contract.yaml --out gen --state state.json
```

### 方式 B:作为 Agent 插件(需平台接入)

各平台通过插件机制加载本仓库描述符:

| 平台 | 描述符 | 说明 |
|------|--------|------|
| Claude Code | `.claude-plugin/plugin.json` + `marketplace.json` | 插件市场安装 |
| OpenClaw / CatClaw | `openclaw.plugin.json` | hooks/skills/agents 注册 |
| CatPaw | 本目录 + `harness-manifest.json` | 原生 skill 发现 |

装好后用斜杠命令(`/start-workflow`、`/contract-generate`)或自然语言触发。

> ⚠️ 完整 Agent 插件形态仍需:平台运行时接入 + 编排 runner 与真实 LLM 主 Agent 打通。当前确定性内核已可用,Agent 全自动 SDLC 待接运行时。

## 卸载

```bash
rm -rf ~/.fe-be-contract-harness
```
