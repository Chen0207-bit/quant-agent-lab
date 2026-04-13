"""Single-process modular agent loop."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from quant_system.agents.execution_agent import ExecutionAgent
from quant_system.agents.meta_agent import AgentLoopResult, MetaAgent
from quant_system.agents.monitor_agent import MonitorAgent
from quant_system.agents.position_agent import PositionAgent
from quant_system.agents.regime_agent import RegimeAgent
from quant_system.agents.risk_agent import RiskAgent
from quant_system.agents.signal_agent import SignalAgent
from quant_system.backtest.history import append_daily_bars
from quant_system.common.models import Bar, Instrument, Order, OrderIntent, RiskDecision
from quant_system.execution.paper import CostConfig
from quant_system.risk.engine import RiskConfig
from quant_system.strategies.base import Strategy


class ModularAgentLoop:
    def __init__(
        self,
        *,
        strategies: Sequence[Strategy],
        instruments: dict[str, Instrument],
        initial_cash: float = 100000.0,
        risk_config: RiskConfig | None = None,
        cost_config: CostConfig | None = None,
        regime_agent: RegimeAgent | None = None,
        monitor_agent: MonitorAgent | None = None,
    ) -> None:
        self.instruments = instruments
        self.regime_agent = regime_agent or RegimeAgent()
        self.signal_agent = SignalAgent(strategies)
        self.position_agent = PositionAgent()
        self.risk_agent = RiskAgent(risk_config)
        self.execution_agent = ExecutionAgent(initial_cash=initial_cash, cost_config=cost_config)
        self.monitor_agent = monitor_agent or MonitorAgent()
        self.meta_agent = MetaAgent(
            regime_agent=self.regime_agent,
            signal_agent=self.signal_agent,
            position_agent=self.position_agent,
            risk_agent=self.risk_agent,
            monitor_agent=self.monitor_agent,
        )

    def run(self, bars_by_date: dict[date, dict[str, Bar]]) -> list[AgentLoopResult]:
        history: dict[str, list[Bar]] = {}
        pending_orders: list[OrderIntent] = []
        results: list[AgentLoopResult] = []

        for trade_date in sorted(bars_by_date):
            bars = bars_by_date[trade_date]
            submitted_orders: list[Order] = []
            if pending_orders:
                pending_decision = _approved_decision(pending_orders)
                submitted_orders = self.execution_agent.submit_approved_orders(pending_decision, bars)
                pending_orders = []

            self.execution_agent.mark_to_market(bars)
            self.execution_agent.settle_trading_day()
            append_daily_bars(history, bars)

            snapshot = self.execution_agent.snapshot(trade_date)
            reconcile = self.execution_agent.reconcile(trade_date)
            result = self.meta_agent.run_day(
                as_of=trade_date,
                history=history,
                portfolio=snapshot,
                bars=bars,
                instruments=self.instruments,
                submitted_orders=submitted_orders,
                fills=list(self.execution_agent.broker.fills),
                reconcile=reconcile,
            )
            pending_orders = list(result.risk_decision.approved_orders)
            results.append(result)
        return results


def _approved_decision(orders: list[OrderIntent]) -> RiskDecision:
    from quant_system.common.models import RiskAction

    return RiskDecision(RiskAction.APPROVE, tuple(orders), tuple(), tuple())

