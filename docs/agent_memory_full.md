# Quant Agent Lab Shared Memory

This document is the handoff memory for another agent or a later session.
It contains project state, architecture decisions, operational facts, and
current blockers.

## Fixed environment

- Write project files only on Ubuntu, not in the Windows workspace
- SSH: `ssh fc@192.168.93.130`
- Project root: `/home/fc/projects/quant-agent-lab`
- Python venv: `/home/fc/projects/quant-agent-lab/.venv`
- Runtime environment: Ubuntu, Node `v22.22.2`, npm `10.9.7`, OpenClaw `2026.4.11`, Codex CLI `0.120.0`
- OpenClaw gateway is running on `*:18789`

## Git state

- Local repo initialized
- `main` branch exists
- `arch/llm-foundation` branch exists
- Remote is `git@github.com:Chen0207-bit/quant-agent-lab.git`
- Current blocker: `git push` from Ubuntu still fails with `Permission denied (publickey)`
- Remote repo nuance: `main` was bootstrapped with a README-only commit through the GitHub API;
  once SSH works, local `main` should replace it with `git push --force-with-lease origin main`
- Public key path: `~/.ssh/id_ed25519.pub`

## Business target

Build a maintainable A-share low-frequency quant system.
It is not a notebook project and not a tutorial replay.

Confirmed scope:

- market: A-share
- frequency: daily / low frequency
- capital: about CNY 100k
- data source: free first, AKShare for MVP
- execution stage: paper-only for MVP
- universe: ETF first, main-board sample stocks for engineering validation
- excluded for MVP: ChiNext, STAR, BSE, live broker APIs
- deployment: Ubuntu single-machine modular monolith

## Architecture baseline

Deterministic control path:

```text
DataAgent -> RegimeAgent -> SignalAgent -> PositionAgent -> RiskAgent -> ExecutionAgent -> MonitorAgent
MetaAgent handles deterministic orchestration and downgrade logic
```

Hard boundaries:

- `DataAgent`: calendar, sync, quality gate, history preparation
- `RegimeAgent`: market state and strategy weights
- `SignalAgent`: target positions only
- `PositionAgent`: convert targets to A-share order intents only
- `RiskAgent`: deterministic veto authority
- `ExecutionAgent`: approved orders only, paper broker only
- `MonitorAgent`: summaries, JSON, manual orders, diagnostics
- `MetaAgent`: deterministic coordination, never overrides risk

## LLM state

LLM support is being added according to the book, but only on the read-only side.

Implemented Phase 1:

- `configs/llm.toml`
- `src/quant_system/llm/base.py`
- `src/quant_system/llm/disabled.py`
- `src/quant_system/llm/audit.py`
- `src/quant_system/llm/artifacts.py`
- `src/quant_system/llm/report_agent.py`
- `src/quant_system/llm/prompts/__init__.py`
- daily pipeline hook after report writing

Scaffold only:

- `src/quant_system/llm/research_agent.py`
- `src/quant_system/llm/sentiment_agent.py`

Rules:

- LLM default is disabled
- LLM must not produce `TargetPosition`, `OrderIntent`, or `RiskDecision`
- LLM failure must not break `daily_pipeline.py`
- LLM writes only report and audit artifacts right now

## Current universe

Configured sample universe:

- ETFs: `510300`, `510500`, `159915`
- Main board samples: `600000`, `600519`, `601318`, `601888`, `000001`, `000333`, `000651`, `002415`

Default exclusions:

- ChiNext: `300/301`
- STAR: `688/689`
- BSE: `8/4`
- ST, suspended, unknown board

## Multi-agent evolution state

Current status is roughly Stage 4-alpha plus Stage 5 deterministic thin layers.

- Stage 1: single-strategy loop validated
- Stage 2: Signal and Risk split; risk veto preserved
- Stage 3: Execution uses approved orders only
- Stage 4: Regime and Meta downgrade logic active
- Stage 5 deterministic pieces added: DataAgent, PositionAgent, MetaAgent
- LLM Phase 1 added: read-only report layer

## Main commands

Compile and unit tests:

```bash
cd /home/fc/projects/quant-agent-lab
.venv/bin/python -m compileall -q src tests scripts main.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Smoke commands:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_backtest_smoke.py
PYTHONPATH=src .venv/bin/python scripts/paper_run_smoke.py
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_smoke.py
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5
```

## Current outputs

End-of-day pipeline writes:

```text
runs/reports/YYYY-MM-DD/
  daily_summary.md
  daily_summary.json
  manual_orders.csv
  data_sync_report.json
  strategy_diagnostics.json
  llm_report.md
  llm_report.json
  llm_audit.jsonl
```

Under default config, `llm_report.json` should show `status = skipped`.

## Latest validation

Latest verified state:

- `compileall`: pass
- `unittest discover -s tests`: pass, 39 tests OK
- `run_backtest_smoke.py`: pass, return `2.63%`, orders `6`, fills `6`
- `paper_run_smoke.py`: pass, `risk_action=APPROVE`, one fill, reconcile consistent
- `run_agent_loop_smoke.py`: pass
- `daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5`: pass
- `runs/reports/2025-01-27/` now includes `llm_report.md`, `llm_report.json`, `llm_audit.jsonl`

## Important blockers

- GitHub SSH write access from Ubuntu is still missing
- Because of that, local commits are possible but remote backup is not yet complete

## Next recommended steps

1. Fix GitHub SSH write access and push `main` and `arch/llm-foundation`
2. Keep strategy work on `strategy/<topic>` branches
3. Extend `LLMResearchAgent` against diagnostics and backtest artifacts, not the trading path
4. Run paper pipeline across at least 5 trading days
5. Only then evaluate text / news features

## Execution principles for the next agent

- Read `docs/?????.md`, `docs/git_workflow.md`, and `docs/llm_architecture_plan.md` first
- Run compile and full tests before changing code
- Keep trading-path changes deterministic
- Add tests for any change that could affect orders, positions, risk, or execution
- Do not claim remote backup is complete until `git push` succeeds
