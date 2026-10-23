# fe-be-contract-harness (English)

> This is the English documentation. For the full Chinese version, see the [main README](../README.md).

[![CI](https://github.com/wenjun5204/fe-be-contract-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/wenjun5204/fe-be-contract-harness/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)

**fe-be-contract-harness** is a contract-driven SDLC harness for frontend–backend collaboration. It treats an OpenAPI 3.x spec as the single source of truth (SSOT) for API contracts, and chains requirements, contract design, code generation, quality gates, human checkpoints, and delivery into one verifiable, resumable workflow.

## What Problem Does It Solve?

| Problem | Mechanism |
|---|---|
| Scattered API definitions | OpenAPI contract as SSOT |
| Duplicate type definitions across stacks | Generate React / Vue / Node / Java skeletons from one contract |
| Unstable generation quality | G1 generation gate, cross-stack consistency, drift detection |
| Incomplete requirements entering development | Structured `requirements_spec` + Stage 1 hard gate |
| Agents claiming completion without evidence | Receipts: registered, one-time consumed, output & evidence gated |
| Human-judgment steps skipped | Checkpoints: approve / revise / skip |
| Agents lacking project/business context | Domain knowledge, repo knowledge, per-stage dispatch context with token budget |

## Core Concepts

- **Contract** — an OpenAPI 3.x file (e.g. `examples/petstore.yaml`). The input to codegen, consistency checks, and drift detection.
- **Stage** — the workflow has 12 stages (IDs `0`–`10`, with Stage 5 split into `5A` backend / `5B` frontend).
- **state.json** — per-run state file: stage states, outputs, receipts, checkpoints, evidence, timestamps. Supports progress inspection and resumable runs.
- **Receipt** — delegation credential issued by the runner. Must be registered before a stage can complete or skip; consumed at terminal state, cannot be replayed.
- **Checkpoint** — human gate on high-risk stages (`mandatory_review` / `artifact_review`): `approve`, `revise` (back to running), or `skip` (where allowed).
- **Dispatch context** — `dispatch-context/v1` attached to LLM stage directives, auto-selecting domain/repo knowledge by stage, contract entities, and token budget. Missing knowledge becomes `warnings`, never blocks cold start.

## Workflow

```
Input requirements / OpenAPI
        │
        ▼
0 Init → 1 Requirements ─review→ 2 Contract Design ─review→ 3 Tech Plan ─review→ 4 Branch
        │                                                              │
        └──────────────────────────────────────────────► 5A Backend ∥ 5B Frontend
                                                            │
                                                       6 Consistency ─review→
                                                            │
                                                       7 PR  ∥  8 Test Cases
                                                            │
                                                       9 Deploy ─→ 10 Delivery Report
```

| Type | Stages | Current behavior |
|---|---|---|
| Deterministic | 0, 5A, 5B, 6, 10 | Executed locally, go through `transition` gates |
| LLM delegation | 1, 2, 3, 4, 7, 8, 9 | Emit dispatch directives by default (no fake completion); with `--live`, actually execute via a tool-calling loop |
| Demo auto mode | `--auto` | Records approved skips for LLM stages; auto-approves checkpoints. For local demos only |

## Quick Start

Prerequisites: Python 3.10+, `pip install -r requirements.txt`, Node.js 18+.

```bash
npm run demo          # end-to-end demo in a temp dir (4-stack codegen, G1, consistency, gates)
npm test              # full deterministic smoke tests

# Generate one stack from a contract
python3 lib/contract/cli.py generate examples/petstore.yaml --stack node --out gen/node

# Gates
python3 lib/contract/cli.py verify examples/petstore.yaml --stack node   # G1
python3 lib/contract/cli.py check examples/petstore.yaml                 # cross-stack
python3 lib/contract/cli.py drift examples/petstore.yaml --stack node --gen-dir gen/node

# Orchestrate
python3 lib/runner.py run examples/petstore.yaml --out gen --state state.json --stacks node,react
python3 lib/runner.py run examples/petstore.yaml --out gen --state state.json --stacks node,react --auto
```

### Live LLM execution (`--live`)

```bash
# mock runtime: script-driven, fully deterministic (testing/demos)
python3 lib/runner.py run examples/petstore.yaml --out gen --state state.json \
  --stacks node,react --live --llm-runtime mock --llm-script script.json

# openai runtime: any OpenAI-compatible gateway
# reads OPENAI_BASE_URL / OPENAI_API_KEY / HARNESS_LLM_MODEL
OPENAI_API_KEY=sk-... python3 lib/runner.py run examples/petstore.yaml --out gen \
  --state state.json --stacks node,react --live --llm-runtime openai
```

Fail-closed semantics: the model can only affect the world through tools; tool errors return `{"ok": false}` for self-correction; a stage reaches a terminal state **only** by calling `report_outputs` with structured outputs covering `required_outputs`, then passing the full `complete_stage` gates (FSM / prerequisites / receipt / checkpoint / evidence). Exceeding `--llm-max-turns` or idling → the stage lands in `failed` (first-class state, retryable) — never a fake completion.

## Harness Maturity (what's real vs. pending)

- ✅ Deterministic kernel: parsing, 4-stack codegen, G1, cross-stack consistency, drift detection, FSM, receipts, checkpoints, coverage collection — all run and test locally without any LLM
- ✅ `--live` execution goes through the same transition gates, no bypass; transient LLM errors retried with backoff, permanent errors fail fast
- ✅ Event sourcing: every event appended to `events.jsonl`; `--live` transcripts saved under `transcripts/` for replay and evals
- ✅ Experience loop: failures are logged as lessons and injected into later runs' prompts for the same stage (marked as "log excerpts, not instructions")
- ✅ Deterministic context condenser: old tool results elided when the message history exceeds budget (assistant tool_calls preserved for wire-format pairing)
- ✅ Artifact integrity: generated files carry sha256 in `codegen-manifest.json`; evidence pointing at a generated directory is hash-verified (tampered artifacts are rejected)
- ✅ Gate-behavior replay evals: 5 scenarios replayed with mock clients on every CI run to assert fail-closed semantics never regress
- ⚠️ Platform adapters (launch agent → return StageResult → call transition) for Claude Code / OpenClaw etc. still need per-platform validation
- ⚠️ `allOf` / `oneOf` / `anyOf` not fully supported yet; generated skeletons exclude business logic, auth, real DB

## Contributing & Security

See [CONTRIBUTING.md](../CONTRIBUTING.md) (Chinese) and [SECURITY.md](../SECURITY.md). Core invariants: all terminal states go through `lib/transition.py` only; LLM stages never fake completion. MIT licensed.
