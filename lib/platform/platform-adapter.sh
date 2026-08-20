#!/usr/bin/env bash
# 平台适配层:检测当前 Agent 运行时。
# M0 阶段:仅做运行时检测(最佳努力);后续阶段补齐工具名映射、平台能力开关与 hook 分发。
set -euo pipefail

detect_platform() {
  # 1. 显式覆盖(最高优先级)
  if [ -n "${HARNESS_PLATFORM:-}" ]; then
    printf '%s\n' "$HARNESS_PLATFORM"
    return 0
  fi

  # 2. 按运行时特征环境变量探测(最佳努力,M0 阶段)
  if [ -n "${OPENCLAW_SESSION_ID:-}${CATCLAW_SESSION:-}" ]; then
    printf 'openclaw\n'; return 0
  fi
  if [ -n "${CATPAW_SESSION:-}${CATPAW_ENV:-}" ]; then
    printf 'catpaw\n'; return 0
  fi
  if [ -n "${CLAUDE_SESSION_ID:-}${CLAUDE_CODE_ENTRYPOINT:-}" ]; then
    printf 'claude-code\n'; return 0
  fi
  if [ -n "${CODEX_SESSION_ID:-}${CODEX_HOME:-}" ]; then
    printf 'codex\n'; return 0
  fi
  if [ -n "${OPENCODE_SESSION:-}" ]; then
    printf 'opencode\n'; return 0
  fi

  # 3. 兜底:未知 / 本地 shell
  printf 'unknown\n'
}

# 直接执行时输出检测结果;被 source 时仅导出函数供复用。
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  detect_platform
fi
