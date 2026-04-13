# Codex Handoff - 2026-04-13

Project path: `/home/fc/projects/quant-agent-lab`
Environment: Ubuntu VM `fc@192.168.93.130`
Status: this turn did not finish the full cross-sectional strategy factory implementation. A subset of core types and helpers was added. The repo currently compiles, but unit tests are failing because callers were not updated yet.

## 1. Baseline state before this turn

Before this turn, the project already had:

- A-share daily / low-frequency / paper-only MVP.
- `ETF multi-window momentum + volatility penalty`.
- `Main-board breakout + amount / limit-up / moving-average` filters.
- `strategy_diagnostics.json`, `daily_summary.json`, `manual_orders.csv`, `data_sync_report.json`.
- Offline research runner `scripts/strategy_research_run.py` writing `config.json`, `candidates.json`, `metrics.json`, `ranking.json`, `strategy_diagnostics.json`, `summary.md`.
- Previous verification from the earlier round: `compileall` passed, `unittest discover -s tests` was green, `daily_pipeline.py --as-of 2025-01-31 ...` and `strategy_research_run.py --use-simulated ...` both ran successfully.

## 2. Intended goal for this turn

The target was to move from a demo strategy layer to an auditable, reproducible, paper-only A-share cross-sectional strategy factory:

- Add `UniverseSnapshot / StrategyContext / ScoredCandidate`.
- Upgrade `SignalAgent` from direct target aggregation to a two-stage flow: ranking first, then portfolio construction.
- Add constraint-aware portfolio construction: single-name cap, industry cap, turnover budget, cash buffer.
- Upgrade the research runner toward a family-based workflow aligned with long-only AQR / MSCI / Barra style processes.

## 3. Files actually changed in this turn

These files were changed successfully, and `compileall` passed after these edits:

1. `src/quant_system/common/models.py`
   - Added `UniverseMember`, `UniverseSnapshot`, `PortfolioConstraints`, `StrategyContext`, `ScoredCandidate`.
   - Expanded `StrategyDiagnosticRecord` with `family`, `rank`, `rank_percentile`, `universe_size`, `peer_distance`, `normalized_features`, `target_weight_before_regime`, `target_weight_after_regime`.

2. `src/quant_system/config/settings.py`
   - Added `UniverseSymbolMetadata`.
   - Added `symbol_metadata` to `UniverseConfig`.
   - `load_universe_config()` now supports `universe.metadata` in TOML.

3. `src/quant_system/data/universe.py`
   - Kept `build_mvp_universe()`.
   - Added `build_universe_snapshot(as_of, instruments, bars, config)`.

4. `src/quant_system/features/factors.py`
   - Added `average_true_range()`.

5. `src/quant_system/strategies/base.py`
   - Added `CrossSectionalStrategy` protocol with `rank_candidates()`, `diagnose()`, and `is_rebalance_day()`.

6. `src/quant_system/portfolio/construction.py`
   - Added constraint helpers for single-name cap, industry cap, gross exposure cap, and turnover budget.

## 4. What did not get applied

The second wave of edits did not get written:

- `src/quant_system/strategies/baseline.py`
- `src/quant_system/agents/signal_agent.py`
- `src/quant_system/agents/meta_agent.py`
- `src/quant_system/app/main_loop.py`
- `src/quant_system/agents/monitor_agent.py`
- `src/quant_system/app/daily_pipeline.py`
- `configs/universe.toml`
- `configs/strategy.toml`
- `scripts/strategy_research_run.py`
- related tests

The failure was not a Python design issue. It was a transport issue when sending large file payloads through Windows PowerShell -> SSH. The concrete error was:

- `The filename or extension is too long.`

That means the repo is in a partial migration state:

- the new schema exists
- the old callers are still present
- tests now fail because of the schema mismatch

## 5. Current verification status

### 5.1 compileall

Command:

```bash
cd /home/fc/projects/quant-agent-lab
.venv/bin/python -m compileall -q src tests scripts main.py
```

Result: passed.

### 5.2 unittest

Command:

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Result: failed. `47 tests` ran with `8 errors`.

The main failure shape is:

```text
TypeError: StrategyDiagnosticRecord.__init__() missing 1 required positional argument: 'family'
```

Main failure sites:

- `src/quant_system/strategies/baseline.py`
- `src/quant_system/agents/signal_agent.py`
- `src/quant_system/app/main_loop.py`
- `scripts/strategy_research_run.py`

Root cause: those files still construct `StrategyDiagnosticRecord` with the old shape.

## 6. Recommended recovery order

### Step 1: restore green tests first

Do not continue feature expansion before compatibility is restored.

1. Update `src/quant_system/strategies/baseline.py`
   - Add `family=` to every `StrategyDiagnosticRecord(...)` call.
   - Restore the current ETF / main-board baseline to compatibility with the new schema.

2. Update `src/quant_system/agents/signal_agent.py`
   - At minimum, make diagnostics compatible with the new schema.

3. Update `src/quant_system/agents/meta_agent.py` and `src/quant_system/app/main_loop.py`
   - Keep them compatible even if `UniverseSnapshot` is not fully wired yet.

4. Update `scripts/strategy_research_run.py`
   - Make the runner work again on the old logic first.

5. Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Goal: get back to green before doing more structural changes.

### Step 2: continue the cross-sectional factory upgrade

After Step 1 is green, continue in this order:

1. `baseline.py`
   - Convert ETF strategy into a real `CrossSectionalStrategy`.
   - Convert main-board breakout into a real `CrossSectionalStrategy`.
   - Add `rank_candidates()`.

2. `signal_agent.py`
   - Move to the two-stage flow:
     - family ranking
     - constraint-aware construction

3. `main_loop.py` and `daily_pipeline.py`
   - Wire in `build_universe_snapshot()`.
   - Write the snapshot into the report directory.

4. `strategy_research_run.py`
   - Upgrade it into a family research runner.
   - Add `universe_snapshot.json`, `failure_analysis.md`, walk-forward output, IC/RankIC, industry exposure.

5. `configs/universe.toml`
   - Expand ETF symbols to a 10-20 liquid ETF sleeve.
   - Expand main-board symbols to a 20-50 liquid leader sleeve.
   - Add `universe.metadata.<symbol>`.

6. `configs/strategy.toml`
   - Add `rebalance_frequency` and `rebalance_interval_days`.
   - Add `defensive_quality`, still allowed to stay `enabled = false` at first.

## 7. Strategy direction that should not change

Research conclusions from the previous multi-agent work were consistent. The implementation should stay aligned with them:

Priority order:

1. `ETF / sector ETF relative strength rotation`
2. `Liquid main-board leader trend / breakout ranking`
3. `Low-vol / quality / dividend` as a later defensive sleeve

Do not prioritize:

- high frequency / intraday microstructure
- shorting / market neutral
- low-liquidity small-cap reversal
- automatic live trading

OpenClaw should stay in research task distribution, tracking, and result collection.
Superpowers should stay in agent workflow discipline and validation checklists.
Neither should enter trading runtime.

## 8. Mature strategy benchmark mapping

The correct benchmark direction is:

- AQR-style long-only momentum / defensive equity sleeves
- MSCI / Barra style factor exposure, risk constraints, portfolio construction, and attribution

Not:

- WorldQuant / Renaissance style high-frequency alpha factory
- black-box LLM trading decisions

## 9. Operational lesson from this failed attempt

The blocker was transport size, not project logic. Next time:

1. Do not send huge multi-file payloads in one PowerShell -> SSH command.
2. Write only one or two files per command.
3. Prefer Ubuntu-side temp files and smaller atomic replacements.
4. Restore compatibility first, then continue the larger refactor.

## 10. Purpose of this document

This handoff is meant to describe the real repo state for the next engineer or agent:

- what was already in the project
- what changed in this turn
- what failed
- why tests are broken now
- how to resume safely without losing direction
