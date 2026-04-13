# Architecture

The MVP targets A-share daily and low-frequency workflows: fetch and cache daily market data, normalize and validate it, build signals, convert targets into A-share compliant orders, apply deterministic risk gates, execute through paper trading, then produce audit logs and reports.

| Module | Responsibility |
|---|---|
| `common` | Shared dataclasses, enums, IDs, money/date helpers |
| `data` | Data adapters, instrument classification, quality checks |
| `features` | Factor and feature snapshots |
| `strategies` | Signal and target generation only |
| `portfolio` | Target sizing, lot rounding, cash constraints |
| `risk` | Deterministic hard gates and veto decisions |
| `backtest` | Daily event loop and execution simulation |
| `execution` | Paper broker, manual export, order/fill lifecycle |
| `monitoring` | Health checks, reports, audit-friendly output |
| `agents` | Research and review templates, not runtime control |

Agents can propose, explain, review, and summarize. They cannot approve orders, place orders, edit production risk parameters, or override deterministic checks.
