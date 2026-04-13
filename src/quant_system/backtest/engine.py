"""Lightweight daily event backtest for A-share MVP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_system.backtest.history import append_daily_bars
from quant_system.common.models import Bar, Fill, Instrument, Order, OrderIntent
from quant_system.execution.paper import CostConfig, PaperBroker
from quant_system.portfolio.sizing import targets_to_order_intents
from quant_system.risk.engine import RiskConfig, RiskEngine
from quant_system.strategies.base import Strategy


@dataclass(frozen=True, slots=True)
class EquityPoint:
    trade_date: date
    equity: float
    cash: float


@dataclass(frozen=True, slots=True)
class BacktestResult:
    equity_curve: tuple[EquityPoint, ...]
    orders: tuple[Order, ...]
    fills: tuple[Fill, ...]
    rejected_orders: tuple[str, ...]


class DailyEventBacktester:
    def __init__(
        self,
        *,
        strategy: Strategy,
        instruments: dict[str, Instrument],
        initial_cash: float = 100000.0,
        risk_config: RiskConfig | None = None,
        cost_config: CostConfig | None = None,
    ) -> None:
        self.strategy = strategy
        self.instruments = instruments
        self.broker = PaperBroker(initial_cash=initial_cash, cost_config=cost_config)
        self.risk_engine = RiskEngine(risk_config)

    def run(self, bars_by_date: dict[date, dict[str, Bar]]) -> BacktestResult:
        pending_orders: list[OrderIntent] = []
        history: dict[str, list[Bar]] = {}
        equity_curve: list[EquityPoint] = []
        rejected: list[str] = []

        for trade_date in sorted(bars_by_date):
            bars = bars_by_date[trade_date]
            if pending_orders:
                self.broker.submit_orders(pending_orders, bars)
                pending_orders = []
            self.broker.mark_to_market(bars)
            self.broker.settle_trading_day()
            append_daily_bars(history, bars)

            snapshot = self.broker.snapshot(trade_date)
            targets = self.strategy.generate_targets(trade_date, history, snapshot)
            intents = targets_to_order_intents(
                strategy_id=self.strategy.strategy_id,
                targets=targets,
                portfolio=snapshot,
                prices=bars,
                instruments=self.instruments,
            )
            decision = self.risk_engine.evaluate_orders(
                as_of=trade_date,
                orders=intents,
                portfolio=snapshot,
                bars=bars,
                instruments=self.instruments,
            )
            pending_orders = list(decision.approved_orders)
            rejected.extend(decision.reasons)
            end_snapshot = self.broker.snapshot(trade_date)
            equity_curve.append(EquityPoint(trade_date, end_snapshot.equity, end_snapshot.cash))

        return BacktestResult(
            equity_curve=tuple(equity_curve),
            orders=tuple(self.broker.orders.values()),
            fills=tuple(self.broker.fills),
            rejected_orders=tuple(rejected),
        )
