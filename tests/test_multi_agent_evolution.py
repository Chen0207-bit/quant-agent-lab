import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from quant_system.agents.data_agent import DataAgent, DataAgentError
from quant_system.agents.execution_agent import ExecutionAgent
from quant_system.agents.meta_agent import MetaAgent
from quant_system.agents.monitor_agent import MonitorAgent
from quant_system.agents.position_agent import PositionAgent
from quant_system.agents.regime_agent import RegimeState
from quant_system.agents.risk_agent import RiskAgent
from quant_system.agents.signal_agent import SignalAgent
from quant_system.app.main_loop import ModularAgentLoop
from quant_system.common.models import (
    Bar,
    OrderIntent,
    PositionSnapshot,
    ReconcileReport,
    RiskAction,
    RiskDecision,
    RiskRejection,
    Side,
    TargetPosition,
)
from quant_system.data.a_share_rules import classify_symbol
from quant_system.data.calendar import TradingCalendar
from quant_system.data.manager import DataSyncReport
from quant_system.execution.manual_export import export_manual_orders
from quant_system.execution.paper import CostConfig
from quant_system.risk.engine import RiskConfig
from quant_system.strategies.baseline import EtfMomentumStrategy


class DummyStrategy:
    strategy_id = "etf_momentum"

    def generate_targets(self, as_of: date, history: dict[str, list[Bar]], portfolio: PositionSnapshot) -> list[TargetPosition]:
        return [TargetPosition("510300", 0.4, "dummy_target")]


class AlwaysUncertainRegime:
    def detect(self, history: dict[str, list[Bar]]) -> RegimeState:
        return RegimeState("uncertain", 0.3, {"etf_momentum": 0.33, "default": 0.33}, "test_uncertain")


class AlwaysTrendingRegime:
    def detect(self, history: dict[str, list[Bar]]) -> RegimeState:
        return RegimeState("trending", 0.7, {"etf_momentum": 1.0, "default": 1.0}, "test_trending")


class ExplodingRiskAgent:
    def review_orders(self, **kwargs) -> RiskDecision:
        raise RuntimeError("boom")


class FailingManager:
    report = DataSyncReport(("510300",), tuple(), ("510300",), 0, False, ("510300: failed",))

    def sync_history(self, symbols, start, end, dataset="silver") -> DataSyncReport:
        return self.report


class MultiAgentEvolutionTest(unittest.TestCase):
    def test_stage1_single_strategy_loop_runs_to_paper_fill(self) -> None:
        symbol = "510300"
        instruments = {symbol: classify_symbol(symbol)}
        bars_by_date = _bars_by_date(symbol, days=30, start_price=4.0, step=0.03)
        loop = ModularAgentLoop(
            strategies=(EtfMomentumStrategy("etf_momentum", symbols=(symbol,), lookback_days=5, max_weight_per_symbol=0.4),),
            instruments=instruments,
            risk_config=RiskConfig(max_position_weight=0.5),
            cost_config=CostConfig(slippage_bps=0),
        )
        results = loop.run(bars_by_date)
        self.assertEqual(len(results), 30)
        self.assertTrue(any(result.targets for result in results), "single strategy should eventually emit targets")
        self.assertTrue(any(result.fills for result in results), "paper broker should eventually fill approved orders")

    def test_stage2_signal_outputs_targets_and_risk_vetoes_invalid_board(self) -> None:
        signal_agent = SignalAgent([DummyStrategy()])
        regime = RegimeState("trending", 0.7, {"etf_momentum": 0.5, "default": 0.5}, "test")
        targets = signal_agent.generate_targets(date(2025, 1, 2), {}, PositionSnapshot(date(2025, 1, 2), 100000, {}), regime)
        self.assertIsInstance(targets[0], TargetPosition)
        self.assertFalse(isinstance(targets[0], OrderIntent))

        risk_agent = RiskAgent(RiskConfig())
        decision = risk_agent.review_orders(
            as_of=date(2025, 1, 2),
            orders=[_intent("300750", Side.BUY, 100)],
            portfolio=PositionSnapshot(date(2025, 1, 2), 100000, {}),
            bars={"300750": _bar("300750", date(2025, 1, 2), 10.0)},
            instruments={"300750": classify_symbol("300750")},
        )
        self.assertEqual(decision.action, RiskAction.REJECT)
        self.assertIn("outside MVP universe", decision.reasons[0])

    def test_stage3_execution_and_manual_export_only_use_approved_orders(self) -> None:
        execution_agent = ExecutionAgent(initial_cash=100000, cost_config=CostConfig(slippage_bps=0))
        rejected_decision = RiskDecision(
            RiskAction.REJECT,
            tuple(),
            (RiskRejection("ord-rejected", "510300", "blocked"),),
            ("blocked",),
        )
        submitted = execution_agent.submit_approved_orders(
            rejected_decision,
            {"510300": _bar("510300", date(2025, 1, 2), 4.0)},
        )
        self.assertEqual(submitted, [])
        self.assertEqual(execution_agent.broker.orders, {})

        approved = _intent("510300", Side.BUY, 100)
        with tempfile.TemporaryDirectory() as tmpdir:
            export_manual_orders(Path(tmpdir) / "manual_orders.csv", list(RiskDecision(RiskAction.APPROVE, (approved,), tuple(), tuple()).approved_orders))
            content = (Path(tmpdir) / "manual_orders.csv").read_text(encoding="utf-8")
        self.assertIn(approved.order_id, content)
        self.assertNotIn("ord-rejected", content)

    def test_stage5_data_agent_stops_on_sync_failure(self) -> None:
        agent = DataAgent(
            manager=FailingManager(),
            calendar=TradingCalendar((date(2025, 1, 2),)),
        )
        with self.assertRaises(DataAgentError) as raised:
            agent.prepare_history(as_of=date(2025, 1, 2), symbols=("510300",), lookback_days=5)
        self.assertIs(raised.exception.sync_report, FailingManager.report)

    def test_stage5_position_agent_still_requires_risk_veto(self) -> None:
        position_agent = PositionAgent()
        portfolio = PositionSnapshot(date(2025, 1, 2), 100000, {})
        bars = {"300750": _bar("300750", date(2025, 1, 2), 10.0)}
        instruments = {"300750": classify_symbol("300750")}
        intents = position_agent.build_order_intents(
            as_of=date(2025, 1, 2),
            targets=[TargetPosition("300750", 0.10, "not_allowed")],
            portfolio=portfolio,
            bars=bars,
            instruments=instruments,
        )
        self.assertEqual(len(intents), 1)
        decision = RiskAgent().review_orders(
            as_of=date(2025, 1, 2),
            orders=intents,
            portfolio=portfolio,
            bars=bars,
            instruments=instruments,
        )
        self.assertEqual(decision.action, RiskAction.REJECT)

    def test_stage5_meta_agent_blocks_new_openings_when_regime_uncertain(self) -> None:
        meta = MetaAgent(
            regime_agent=AlwaysUncertainRegime(),
            signal_agent=SignalAgent([DummyStrategy()]),
            position_agent=PositionAgent(),
            risk_agent=RiskAgent(),
            monitor_agent=MonitorAgent(),
        )
        result = meta.run_day(
            as_of=date(2025, 1, 2),
            history={"510300": [_bar("510300", date(2025, 1, 2), 4.0)]},
            portfolio=PositionSnapshot(date(2025, 1, 2), 100000, {}),
            bars={"510300": _bar("510300", date(2025, 1, 2), 4.0)},
            instruments={"510300": classify_symbol("510300")},
            submitted_orders=[],
            fills=[],
            reconcile=ReconcileReport(
                as_of=date(2025, 1, 2),
                cash=100000,
                equity=100000,
                unrealized_pnl=0,
                is_consistent=True,
                reasons=tuple(),
            ),
        )
        self.assertEqual(result.meta_decision.mode, "defensive_hold")
        self.assertEqual(result.targets, tuple())
        self.assertEqual(result.risk_decision.approved_orders, tuple())

    def test_stage5_meta_agent_fails_closed_on_risk_error(self) -> None:
        meta = MetaAgent(
            regime_agent=AlwaysTrendingRegime(),
            signal_agent=SignalAgent([DummyStrategy()]),
            position_agent=PositionAgent(),
            risk_agent=ExplodingRiskAgent(),
            monitor_agent=MonitorAgent(),
        )
        result = meta.run_day(
            as_of=date(2025, 1, 2),
            history={"510300": [_bar("510300", date(2025, 1, 2), 4.0)]},
            portfolio=PositionSnapshot(date(2025, 1, 2), 100000, {}),
            bars={"510300": _bar("510300", date(2025, 1, 2), 4.0)},
            instruments={"510300": classify_symbol("510300")},
            submitted_orders=[],
            fills=[],
            reconcile=ReconcileReport(
                as_of=date(2025, 1, 2),
                cash=100000,
                equity=100000,
                unrealized_pnl=0,
                is_consistent=True,
                reasons=tuple(),
            ),
        )
        self.assertEqual(result.risk_decision.action, RiskAction.LIQUIDATE_ONLY)
        self.assertEqual(result.risk_decision.approved_orders, tuple())
        self.assertIn("risk_agent_error", result.risk_decision.reasons[0])


def _bars_by_date(symbol: str, *, days: int, start_price: float, step: float) -> dict[date, dict[str, Bar]]:
    trade_date = date(2025, 1, 1)
    price = start_price
    bars_by_date = {}
    for idx in range(days):
        price += step
        day = trade_date + timedelta(days=idx)
        bars_by_date[day] = {symbol: _bar(symbol, day, price)}
    return bars_by_date


def _bar(symbol: str, trade_date: date, price: float) -> Bar:
    return Bar(symbol, trade_date, price, price * 1.01, price * 0.99, price, 1000000, limit_up=price * 1.1, limit_down=price * 0.9)


def _intent(symbol: str, side: Side, qty: int) -> OrderIntent:
    return OrderIntent(
        order_id=f"ord-{symbol}-{side.value}-{qty}",
        strategy_id="test",
        signal_id=None,
        symbol=symbol,
        side=side,
        qty=qty,
        limit_price=None,
        reason="test",
        created_at=datetime.now(timezone.utc),
    )


if __name__ == "__main__":
    unittest.main()

