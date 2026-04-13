# LLM Architecture Plan

This document describes how LLM support is being added to Quant Agent Lab.
The system stays deterministic on the trading path; LLM is only used for
reporting, research assistance, and future text analysis.

## Core rules

- LLM is disabled by default in `configs/llm.toml`
- LLM must not return `TargetPosition`, `OrderIntent`, or `RiskDecision`
- LLM failure must not block `daily_pipeline.py`
- LLM failure must not invalidate offline research artifacts
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

## Phase 2: Research Agent (implemented on the offline path)

Implemented pieces:

- `src/quant_system/llm/research_agent.py`
- `load_research_artifacts(...)` in `src/quant_system/llm/artifacts.py`
- `scripts/strategy_research_run.py` hook after deterministic artifact generation

Execution point:

```text
strategy_research_run.py
  -> write deterministic research artifacts
  -> LLMResearchAgent.propose_experiments(...)
```

Deterministic inputs remain authoritative:

- `config.json`
- `candidates.json`
- `metrics.json`
- `ranking.json`
- `strategy_diagnostics.json`
- `summary.md`

Research LLM outputs:

- `llm_research.md`
- `llm_research.json`
- `llm_audit.jsonl`

Current JSON contract:

- `agent_name`
- `status`
- `provider`
- `model`
- `prompt_hash`
- `input_artifacts`
- `best_candidate_id`
- `research_summary`
- `recommended_experiments`
- `promotion_assessment`
- `metadata`

`promotion_assessment` contains:

- `recommended: bool`
- `rationale: str`

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

## Phase 3: Sentiment / News Agent (scaffold only)

`LLMSentimentAgent` exists as a scaffold only. If text sources are added later,
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
LLM runs only after report artifacts are written or after offline research artifacts are written
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
PYTHONPATH=src .venv/bin/python scripts/strategy_research_run.py --use-simulated --symbols 510300,510500,600000 --end 2025-01-31
```

Expected research outputs when research LLM is enabled:

- `llm_research.md`
- `llm_research.json`
- `llm_audit.jsonl`

## Explicitly forbidden

- LLM generates orders
- LLM computes live position sizes
- LLM edits `risk.toml`
- LLM edits strategy config
- LLM disables stop or cash buffer rules
- LLM triggers paper or live execution
