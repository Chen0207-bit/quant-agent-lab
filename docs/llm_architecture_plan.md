# LLM Architecture Plan

This document describes how LLM support is being added to Quant Agent Lab.
The system stays deterministic on the trading path; LLM is only used for
reporting, research assistance, and future text analysis.

## Core rules

- LLM is disabled by default in `configs/llm.toml`
- LLM must not return `TargetPosition`, `OrderIntent`, or `RiskDecision`
- LLM failure must not block `daily_pipeline.py`
- Every LLM output must leave an audit record

## Phase 1: Report Agent (implemented)

Implemented files:

- `src/quant_system/llm/base.py`
- `src/quant_system/llm/disabled.py`
- `src/quant_system/llm/audit.py`
- `src/quant_system/llm/artifacts.py`
- `src/quant_system/llm/report_agent.py`
- `src/quant_system/llm/prompts/__init__.py`

Execution point:

```text
MonitorAgent.write_daily_outputs(...)
  -> LLMReportAgent.review_daily_report(...)
```

Inputs:

- `daily_summary.md`
- `daily_summary.json`
- `data_sync_report.json`
- `strategy_diagnostics.json`

Outputs:

- `llm_report.md`
- `llm_report.json`
- `llm_audit.jsonl`

With `provider = "disabled"`, the agent writes a placeholder report and audit
entry without making any model call.

## Audit fields

`LLMAuditRecord` includes:

- `run_id`
- `as_of`
- `agent_name`
- `provider`
- `model`
- `prompt_hash`
- `input_artifacts`
- `output_path`
- `recommended_actions`
- `accepted_by_human`
- `accepted_by_program`
- `final_decision_reference`
- `status`
- `error`

## Phase 2: Research Agent (scaffold only)

`LLMResearchAgent` exists as a scaffold. It may later:

- read `strategy_diagnostics.json` and backtest outputs
- propose experiments
- explain parameter sensitivity and data issues

It must not:

- edit code
- edit configs
- write signals into the trading path
- override risk logic

## Phase 3: Sentiment / News Agent (scaffold only)

`LLMSentimentAgent` also exists as a scaffold. If text sources are added later,
we require:

- local caching of raw text and metadata
- `source_url` and `source_time`
- prompt and model audit data
- research-only usage first; no direct signal routing

## Relationship to the trading path

The deterministic control path stays unchanged:

```text
DataAgent -> RegimeAgent -> SignalAgent -> PositionAgent -> RiskAgent -> ExecutionAgent -> MonitorAgent
MetaAgent handles deterministic orchestration and downgrade logic
LLM runs only after report artifacts are written
```

That means:

- `RiskAgent` keeps hard veto power
- `ExecutionAgent` still uses approved orders only
- `MetaAgent` remains deterministic
- LLM is outside the approval path

## Config

Current `configs/llm.toml`:

```toml
[llm]
enabled = false
provider = "disabled"
model = "disabled"
artifacts_dir = "runs/reports"

[llm.report_agent]
enabled = true

[llm.research_agent]
enabled = false

[llm.sentiment_agent]
enabled = false
```

## Current validation

```bash
cd /home/fc/projects/quant-agent-lab
.venv/bin/python -m compileall -q src tests scripts main.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5
```

Expected outputs in `runs/reports/2025-01-27/`:

- `llm_report.md`
- `llm_report.json`
- `llm_audit.jsonl`

## Explicitly forbidden

- LLM generates orders
- LLM computes live position sizes
- LLM edits `risk.toml`
- LLM disables stop or cash buffer rules
- LLM triggers paper or live execution
