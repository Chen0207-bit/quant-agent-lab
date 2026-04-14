import unittest
from datetime import date, timedelta

from quant_system.agents.regime_agent import RegimeAgent
from quant_system.app.preflight_validation import run_preflight_validation
from quant_system.common.models import Bar, PortfolioConstraints, ScoredCandidate
from quant_system.data.a_share_rules import classify_symbol


class DummyValidationStrategy:
    strategy_id = "validation_strategy"
    family = "etf"
    rebalance_frequency = "daily"

    def __init__(self, selected_symbol: str, rejected_symbol: str) -> None:
        self.selected_symbol = selected_symbol
        self.rejected_symbol = rejected_symbol
        self.symbols = (selected_symbol, rejected_symbol)

    def rank_candidates(self, context, history, portfolio):
        return [
            ScoredCandidate(
                strategy_id=self.strategy_id,
                family=self.family,
                symbol=self.selected_symbol,
                score=1.0,
                eligible=True,
                selected=True,
                rank=1,
                rank_percentile=1.0,
                peer_distance=None,
                raw_features={},
                universe_size=2,
                target_weight=0.5,
            ),
            ScoredCandidate(
                strategy_id=self.strategy_id,
                family=self.family,
                symbol=self.rejected_symbol,
                score=0.0,
                eligible=False,
                selected=False,
                rank=2,
                rank_percentile=0.5,
                peer_distance=None,
                raw_features={},
                universe_size=2,
                target_weight=0.0,
                rejection_reason="score_below_min_momentum",
            ),
        ]

    def generate_targets(self, as_of, history, portfolio):
        return []


class PreflightValidationTest(unittest.TestCase):
    def test_validation_returns_insufficient_data_for_short_window(self) -> None:
        payload = run_preflight_validation(
            as_of=date(2025, 1, 10),
            bars_by_date=_bars_by_date(days=10, selected_step=0.02, rejected_step=-0.01),
            strategies=(DummyValidationStrategy("510500", "510300"),),
            instruments={symbol: classify_symbol(symbol) for symbol in ("510300", "510500")},
            regime_agent=RegimeAgent(),
            portfolio_constraints=PortfolioConstraints(max_position_weight=1.0, max_industry_weight=1.0, turnover_budget=1.0, min_cash_buffer_pct=0.0),
            forward_return_horizons=(1, 5),
        )
        self.assertEqual(payload["validation_status"], "insufficient_data")
        self.assertGreaterEqual(len(payload["warnings"]), 1)

    def test_validation_returns_pass_when_selected_outperforms_rejected(self) -> None:
        payload = run_preflight_validation(
            as_of=date(2025, 2, 19),
            bars_by_date=_bars_by_date(days=50, selected_step=0.03, rejected_step=-0.01),
            strategies=(DummyValidationStrategy("510500", "510300"),),
            instruments={symbol: classify_symbol(symbol) for symbol in ("510300", "510500")},
            regime_agent=RegimeAgent(),
            portfolio_constraints=PortfolioConstraints(max_position_weight=1.0, max_industry_weight=1.0, turnover_budget=1.0, min_cash_buffer_pct=0.0),
            forward_return_horizons=(1, 5),
        )
        self.assertEqual(payload["validation_status"], "pass")
        self.assertGreater(payload["selected_vs_rejected_spread"]["5"]["spread"], 0)

    def test_validation_returns_warn_when_selected_underperforms_rejected(self) -> None:
        payload = run_preflight_validation(
            as_of=date(2025, 2, 19),
            bars_by_date=_bars_by_date(days=50, selected_step=-0.02, rejected_step=0.02),
            strategies=(DummyValidationStrategy("510500", "510300"),),
            instruments={symbol: classify_symbol(symbol) for symbol in ("510300", "510500")},
            regime_agent=RegimeAgent(),
            portfolio_constraints=PortfolioConstraints(max_position_weight=1.0, max_industry_weight=1.0, turnover_budget=1.0, min_cash_buffer_pct=0.0),
            forward_return_horizons=(1, 5),
        )
        self.assertEqual(payload["validation_status"], "warn")
        self.assertLessEqual(payload["selected_vs_rejected_spread"]["5"]["spread"], 0)


def _bars_by_date(*, days: int, selected_step: float, rejected_step: float):
    start = date(2025, 1, 1)
    selected_price = 4.0
    rejected_price = 5.0
    rows = {}
    for idx in range(days):
        trade_date = start + timedelta(days=idx)
        selected_price = max(0.5, selected_price * (1.0 + selected_step))
        rejected_price = max(0.5, rejected_price * (1.0 + rejected_step))
        rows[trade_date] = {
            "510500": _bar("510500", trade_date, selected_price),
            "510300": _bar("510300", trade_date, rejected_price),
        }
    return rows


def _bar(symbol: str, trade_date: date, close: float) -> Bar:
    return Bar(
        symbol=symbol,
        trade_date=trade_date,
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=1_000_000,
        amount=close * 1_000_000,
        limit_up=close * 1.10,
        limit_down=close * 0.90,
    )


if __name__ == "__main__":
    unittest.main()
