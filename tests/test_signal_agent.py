import unittest
from datetime import date, timedelta

from quant_system.agents.regime_agent import RegimeState
from quant_system.agents.signal_agent import SignalAgent
from quant_system.common.models import (
    Bar,
    PortfolioConstraints,
    Position,
    PositionSnapshot,
    ScoredCandidate,
    TargetPosition,
    UniverseMember,
    UniverseSnapshot,
)
from quant_system.strategies.baseline import EtfMomentumStrategy


class DummyStrategy:
    strategy_id = "etf_momentum"

    def generate_targets(self, as_of: date, history: dict[str, list[Bar]], portfolio: PositionSnapshot) -> list[TargetPosition]:
        return [TargetPosition("510300", 0.5, "dummy")]




class SingleCandidateStrategy:
    strategy_id = "single_candidate"
    family = "test_family"
    rebalance_frequency = "daily"

    def rank_candidates(
        self,
        context,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[ScoredCandidate]:
        return [
            ScoredCandidate(
                strategy_id=self.strategy_id,
                family=self.family,
                symbol="510500",
                score=1.0,
                eligible=True,
                selected=True,
                rank=1,
                rank_percentile=1.0,
                peer_distance=None,
                raw_features={},
                universe_size=1,
                target_weight=0.4,
            )
        ]

    def generate_targets(self, as_of: date, history: dict[str, list[Bar]], portfolio: PositionSnapshot) -> list[TargetPosition]:
        return []


class SignalAgentTest(unittest.TestCase):
    def test_regime_weight_scales_target(self) -> None:
        agent = SignalAgent([DummyStrategy()])
        regime = RegimeState("trending", 0.7, {"etf_momentum": 0.7, "default": 0.1}, "test")
        targets = agent.generate_targets(
            date(2025, 1, 2),
            {},
            PositionSnapshot(date(2025, 1, 2), 100000, {}),
            regime,
            portfolio_constraints=PortfolioConstraints(
                max_position_weight=1.0,
                max_industry_weight=1.0,
                turnover_budget=1.0,
                min_cash_buffer_pct=0.0,
            ),
        )
        self.assertEqual(len(targets), 1)
        self.assertAlmostEqual(targets[0].target_weight, 0.35)

    def test_cross_sectional_candidates_are_ranked_and_constrained(self) -> None:
        as_of = date(2025, 1, 12)
        history = {
            "510300": _bars("510300", days=10, step=0.01),
            "510500": _bars("510500", days=10, step=0.03),
        }
        strategy = EtfMomentumStrategy(
            "etf_momentum",
            symbols=("510300", "510500"),
            lookback_days=5,
            top_n=2,
            max_weight_per_symbol=0.4,
            volatility_penalty=0.0,
        )
        agent = SignalAgent([strategy])
        regime = RegimeState("trending", 0.8, {"etf_momentum": 1.0, "default": 1.0}, "test")
        universe_snapshot = UniverseSnapshot(
            as_of,
            {
                "510300": UniverseMember("510300", "ETF", "ETF", industry="broad_beta"),
                "510500": UniverseMember("510500", "ETF", "ETF", industry="small_mid_beta"),
            },
        )
        constraints = PortfolioConstraints(
            max_position_weight=0.30,
            max_industry_weight=1.00,
            turnover_budget=1.00,
            min_cash_buffer_pct=0.0,
        )

        targets = agent.generate_targets(
            as_of,
            history,
            PositionSnapshot(as_of, 100000, {}),
            regime,
            universe_snapshot=universe_snapshot,
            portfolio_constraints=constraints,
        )

        self.assertEqual({target.symbol for target in targets}, {"510300", "510500"})
        self.assertTrue(all(target.target_weight <= 0.30 for target in targets))
        diagnostics = agent.diagnose_strategies(as_of, history, PositionSnapshot(as_of, 100000, {}))
        by_symbol = {record.symbol: record for record in diagnostics}
        self.assertEqual(by_symbol["510500"].family, "etf")
        self.assertEqual(by_symbol["510500"].rank, 1)
        self.assertEqual(by_symbol["510500"].universe_size, 2)
        self.assertAlmostEqual(by_symbol["510500"].target_weight_before_regime, 0.4)
        self.assertAlmostEqual(by_symbol["510500"].target_weight_after_regime, 0.4)

    def test_turnover_budget_can_retain_existing_position_reason(self) -> None:
        as_of = date(2025, 1, 12)
        agent = SignalAgent([SingleCandidateStrategy()])
        regime = RegimeState("trending", 0.8, {"single_candidate": 1.0, "default": 1.0}, "test")
        portfolio = PositionSnapshot(
            as_of,
            cash=60000,
            positions={"510300": Position("510300", qty=10000, available_qty=10000, avg_cost=4.0, market_price=4.0)},
        )

        plan = agent.generate_signal_plan(
            as_of=as_of,
            history={},
            portfolio=portfolio,
            regime=regime,
            portfolio_constraints=PortfolioConstraints(
                max_position_weight=1.0,
                max_industry_weight=1.0,
                turnover_budget=0.2,
                min_cash_buffer_pct=0.0,
            ),
        )

        by_symbol = {target.symbol: target for target in plan.targets}
        self.assertIn("510300", by_symbol)
        self.assertIn("510500", by_symbol)
        self.assertIn("retains_existing_position", by_symbol["510300"].reason)



def _bars(symbol: str, *, days: int, step: float) -> list[Bar]:
    rows: list[Bar] = []
    start = date(2025, 1, 1)
    price = 4.0
    for idx in range(days):
        price += step
        trade_date = start + timedelta(days=idx)
        rows.append(
            Bar(
                symbol=symbol,
                trade_date=trade_date,
                open=price * 0.99,
                high=price * 1.01,
                low=price * 0.98,
                close=price,
                volume=1_000_000,
                amount=price * 1_000_000,
                limit_up=price * 1.10,
                limit_down=price * 0.90,
            )
        )
    return rows


if __name__ == "__main__":
    unittest.main()
