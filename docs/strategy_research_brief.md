# Strategy Research Brief: A-share Paper MVP

This brief is for the next strategy-research agent. It describes the current strategy layer, research boundaries, system integration points, and the next evolution steps. This is not investment advice. The current strategy layer is still a paper-only engineering baseline.

## 1. System Boundary

Project path: `/home/fc/projects/quant-agent-lab`

Current scope:

- Market: China A-share.
- Frequency: daily / low-frequency.
- Capital assumption: about CNY 100,000.
- Data source: AKShare free data.
- Execution stage: paper trading only; no live broker API.
- Default runner: end-of-day batch script `scripts/daily_pipeline.py`, not a long-running realtime service.
- Strategy purpose: validate the engineering loop, risk boundaries, reporting flow, and agent collaboration. Do not use as live trading logic.

Forbidden:

- Strategies must not create `Order` or bypass `RiskAgent`.
- LLM agents must not generate orders, size positions, edit risk parameters, or trigger execution.
- `manual_orders.csv` is for human review only, not an automatic trading file.
- The sample universe and signals are not investment recommendations.

## 2. Default Universe

Default universe comes from `configs/universe.toml`:

```text
ETF: 510300, 510500, 159915
Main-board engineering sample: 600000, 600519, 601318, 601888, 000001, 000333, 000651, 002415
```

MVP excludes ChiNext, STAR Market, Beijing Stock Exchange, ST, suspended, and unknown instruments. If `--symbols` is passed, the report tracks only that explicit subset.

## 3. Current Strategy Families

The project still has two baseline families, but they now include auditable diagnostics:

```text
EtfMomentumStrategy        # ETF multi-window momentum plus volatility penalty
MainBoardBreakoutStrategy  # main-board breakout plus amount/limit-up/MA filters
```

Strategies only return `TargetPosition`. `SignalAgent` aggregates and applies Regime weights, `PositionAgent` converts targets into `OrderIntent`, and every intent must pass `RiskAgent` before paper execution.

Current `configs/strategy.toml`:

```toml
[strategy.etf_momentum]
enabled = true
lookback_days = 20
lookback_windows = [20, 60, 120]
window_weights = [0.5, 0.3, 0.2]
volatility_window = 60
volatility_penalty = 0.25
top_n = 2
min_momentum = 0.0
max_weight_per_symbol = 0.25

[strategy.main_board_breakout]
enabled = true
lookback_days = 20
top_n = 5
max_weight_per_symbol = 0.15
min_amount_cny = 10000000
moving_average_days = 20
```

`MainBoardBreakoutStrategy` uses `min_amount_cny`. When `Bar.amount` is missing or zero, it falls back to `volume * close`.

## 4. ETF Momentum

Class: `EtfMomentumStrategy`

Candidate pool: ETF symbols, normally `510300/510500/159915`, or the ETF subset passed through `--symbols`.

Formula:

```text
weighted_momentum = momentum_20 * 0.5 + momentum_60 * 0.3 + momentum_120 * 0.2
score = weighted_momentum - 0.25 * annualized_volatility_60
```

Rules:

- Data must cover the maximum configured window, currently 120 days.
- `score >= min_momentum` is required for eligibility.
- Candidates are sorted by score and capped by `top_n = 2`.
- Raw target weight is `min(max_weight_per_symbol, 1 / selected_count)`, currently capped at 25%.
- `TargetPosition.reason` includes score, weighted momentum, and volatility.

After Regime scaling, a trending ETF target uses `25% * 0.70 = 17.5%`, which stays under the current `risk.max_position_weight = 20%`.

Remaining gaps: no ETF liquidity filter, premium/discount filter, tracking-error filter, strict weekly/monthly rebalance gate, or explicit turnover-aware optimizer.

## 5. Main-board Breakout

Class: `MainBoardBreakoutStrategy`

Candidate pool: the default 8-symbol main-board engineering sample. The strategy still checks `classify_symbol(symbol).board == Board.MAIN` internally.

Formula:

```text
previous_high = max high over the previous lookback window, excluding the current bar
breakout_score = current close / previous_high - 1
```

Rules:

- Data must cover `max(lookback_days, moving_average_days)`.
- `min_amount_cny` filters illiquid symbols.
- Limit-up buy candidates are filtered before target generation.
- Close must be at or above the configured moving average.
- `breakout_score > 0` is required.
- Candidates are sorted by breakout score and capped by `top_n = 5`.
- Raw target weight is `max_weight_per_symbol = 0.15`.

Remaining gaps: no industry/style/market-cap neutrality, no broader fundamental quality filters, and the 8-symbol universe is still only an engineering sample.

## 6. Regime And Meta Effects

`RegimeAgent` outputs `trending / mean_reverting / crisis / uncertain` with default weights:

```text
trending:        etf_momentum=0.70, main_board_breakout=0.20, defensive=0.10
mean_reverting:  etf_momentum=0.20, main_board_breakout=0.70, defensive=0.10
crisis:          etf_momentum=0.10, main_board_breakout=0.10, defensive=0.80
uncertain:       etf_momentum=0.33, main_board_breakout=0.33, defensive=0.34
```

`MetaAgent` applies stronger safety modes:

- `uncertain`: `defensive_hold`, no new openings.
- `crisis`: `crisis_liquidate`, exits only.
- `trending` / `mean_reverting`: `normal`, targets may proceed to RiskAgent review.

Therefore a strategy can have raw candidates while final `targets = []`. Check diagnostics before assuming the strategy failed.

## 7. Diagnostics And Reports

Daily output directory:

```text
runs/reports/YYYY-MM-DD/
  daily_summary.md
  daily_summary.json
  manual_orders.csv
  data_sync_report.json
  strategy_diagnostics.json
```

`daily_summary.json` includes:

- `strategy_diagnostics_path`: path to full strategy diagnostics.
- `raw_candidate_counts`: eligible/selected/rejected counts per strategy.

`strategy_diagnostics.json` records:

```text
as_of, strategy_id, symbol, eligible, selected, score, raw_features,
target_weight, rejection_reason
```

If `targets = []`, inspect `strategy_diagnostics.json`, `meta_decision`, `risk_action`, and `data_sync` first.

## 8. Offline Research Runner

Command:

```bash
PYTHONPATH=src .venv/bin/python scripts/strategy_research_run.py   --use-simulated   --start 2025-01-01   --end 2025-08-29   --symbols 510300,510500,159915,600000,600519
```

Output:

```text
runs/strategy_research/<timestamp>/
  config.json
  candidates.json
  metrics.json
  ranking.json
  strategy_diagnostics.json
  summary.md
```

Candidate limits: at most 16 ETF parameter candidates and 16 main-board parameter candidates per run. Allowed mutation axes are windows, weights, volatility penalty, amount threshold, `top_n`, and per-symbol weight. The runner must not change risk or execution logic.

## 9. Next Research Priorities

1. Accumulate several paper-run diagnostics and verify that `strategy_diagnostics.json` stays stable before expanding the universe.
2. Add ETF drawdown or moving-average filters and consider weekly/monthly rebalance gates to reduce turnover.
3. Improve main-board research only after data sync and backtest speed are stable: industry exposure, liquidity, pullback confirmation, and ATR-style stop research are later work.
4. Improve validation: IS/OOS split, walk-forward stability, cost/slippage sensitivity, Regime-grouped metrics, max drawdown, turnover, win rate, payoff ratio, and exposure ratio.

## 10. Current Conclusion

Current strategy layer:

```text
small universe + ETF multi-window momentum/volatility penalty + main-board breakout filters + Regime safety gate + deterministic Risk veto + PaperBroker validation
```

The value is reproducible research-to-paper-report infrastructure. The next step is better diagnostics, out-of-sample validation, risk exposure reporting, and report explainability, not direct profit maximization.
