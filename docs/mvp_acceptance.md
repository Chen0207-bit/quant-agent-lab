# MVP Acceptance

1. Data quality checks reject duplicate bars and invalid OHLC data.
2. Main-board filters exclude ChiNext, STAR Market, Beijing Stock Exchange, ST, and suspended instruments.
3. Risk checks reject buy orders at limit-up and sell orders at limit-down.
4. Risk checks enforce T+1 available quantity for sells.
5. Order quantities must be positive and aligned to the instrument lot size.
6. Cash buffer and single-name concentration limits are enforced before paper execution.
7. Paper broker records order status changes and fills.
8. A daily backtest can run from historical bars to equity curve and order/fill history.
9. Each run has a `run_id` suitable for audit and report linkage.

Live trading is not part of MVP acceptance.

## Agent Boundary Acceptance

10. `SignalAgent` outputs `TargetPosition` only; it must not create `OrderIntent` or `Order` objects.
11. `PositionAgent` converts target weights into A-share compliant `OrderIntent` objects, but every intent must still pass `RiskAgent`.
12. `RiskAgent` remains the deterministic veto layer; no Meta, LLM, Signal, Position, or Execution layer may override a rejection.
13. `ExecutionAgent` submits only `RiskDecision.approved_orders`; rejected or unreviewed orders must not enter `PaperBroker`.
14. `DataAgent` must stop the daily pipeline on data sync or quality failure; it must not fabricate trading days or successful reports.
15. `MetaAgent` may orchestrate safe degradation, but it must not directly create orders or approve risk.
16. Runtime LLM agents are out of MVP control flow; they may only produce research, explanation, or report drafts after explicit future integration.

