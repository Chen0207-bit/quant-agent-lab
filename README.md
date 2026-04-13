[中文说明](README.zh-CN.md)

# quant-a-share

A-share low-frequency quant trading MVP for research, backtesting, deterministic risk checks, and paper trading.

This project starts as a modular monolith. Agents are used for research, review, reporting, and task orchestration only. They do not approve orders, override risk rules, or place trades.

## MVP scope

- Market: China A-share cash market.
- Universe: long-horizon ETF rotation first; short-horizon main-board constituents next.
- Exclusions: ChiNext, STAR Market, Beijing Stock Exchange, futures, options, margin, high-frequency trading, live broker execution.
- Data: AKShare first, cached locally; Tushare can be added later as a secondary validation source.
- Execution: `PaperBroker` first; manual export next; VeighNa/XTP or QMT bridge only after paper trading is stable.

## Local workflow

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 scripts/run_backtest_smoke.py
PYTHONPATH=src python3 scripts/run_agent_loop_smoke.py
```

On Ubuntu, the intended production layout is:

```text
/opt/quant-a-share/app
/var/lib/quant-a-share
/etc/quant-a-share/config
/var/log/quant-a-share
/var/backups/quant-a-share
```

## Core flow

```text
AKShare -> raw/silver/gold datasets -> feature snapshots -> strategy signals
 -> target positions -> deterministic RiskEngine -> PaperBroker / ManualExportAdapter
 -> orders, fills, positions, reports, audit logs
```
