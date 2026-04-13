import unittest
from datetime import date, timedelta

from quant_system.common.models import Bar, PositionSnapshot
from quant_system.features.factors import annualized_volatility, breakout_score, momentum, moving_average, weighted_momentum
from quant_system.strategies.baseline import EtfMomentumStrategy, MainBoardBreakoutStrategy


class StrategyEvolutionTest(unittest.TestCase):
    def test_factor_history_boundaries_and_values(self) -> None:
        bars = _bars("510300", days=10, start_price=4.0, step=0.02)
        self.assertIsNone(momentum(bars, 20))
        self.assertGreater(momentum(bars, 5), 0)
        self.assertGreater(weighted_momentum(bars, (3, 5), (0.7, 0.3)), 0)
        self.assertIsNotNone(annualized_volatility(bars, 5))
        self.assertIsNotNone(moving_average(bars, 5))
        self.assertIsNotNone(breakout_score(bars, 5))

    def test_etf_multi_window_momentum_selects_top_candidate_with_weight_cap(self) -> None:
        slow = _bars("510300", days=140, start_price=4.0, step=0.01)
        fast = _bars("510500", days=140, start_price=4.0, step=0.03)
        strategy = EtfMomentumStrategy(
            "etf_momentum",
            symbols=("510300", "510500"),
            lookback_windows=(20, 60, 120),
            window_weights=(0.5, 0.3, 0.2),
            volatility_window=60,
            volatility_penalty=0.0,
            top_n=1,
            max_weight_per_symbol=0.25,
        )
        diagnostics = strategy.diagnose(date(2025, 5, 20), {"510300": slow, "510500": fast}, _portfolio())
        selected = [record for record in diagnostics if record.selected]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].symbol, "510500")
        self.assertAlmostEqual(selected[0].target_weight, 0.25)
        self.assertIn("momentum_120", selected[0].raw_features)

    def test_main_board_breakout_filters_amount_limit_up_board_and_trend(self) -> None:
        high_amount = _bars("600000", days=40, start_price=10.0, step=1.00, amount=20_000_000)
        low_amount = _bars("600519", days=40, start_price=10.0, step=1.00, amount=100_000)
        limit_up = _bars("601318", days=40, start_price=10.0, step=1.00, amount=20_000_000, force_limit_up=True)
        non_main = _bars("300750", days=40, start_price=10.0, step=1.00, amount=20_000_000)
        weak_trend = _bars("000001", days=40, start_price=20.0, step=-0.10, amount=20_000_000)
        strategy = MainBoardBreakoutStrategy(
            "main_board_breakout",
            symbols=("600000", "600519", "601318", "300750", "000001"),
            lookback_days=20,
            top_n=5,
            min_amount_cny=10_000_000,
            moving_average_days=20,
        )
        diagnostics = strategy.diagnose(
            date(2025, 2, 10),
            {
                "600000": high_amount,
                "600519": low_amount,
                "601318": limit_up,
                "300750": non_main,
                "000001": weak_trend,
            },
            _portfolio(),
        )
        by_symbol = {record.symbol: record for record in diagnostics}
        self.assertTrue(by_symbol["600000"].selected)
        self.assertEqual(by_symbol["600519"].rejection_reason, "amount_below_min_amount_cny")
        self.assertEqual(by_symbol["601318"].rejection_reason, "blocked_limit_up_buy")
        self.assertEqual(by_symbol["300750"].rejection_reason, "not_main_board")
        self.assertEqual(by_symbol["000001"].rejection_reason, "below_moving_average")


def _portfolio() -> PositionSnapshot:
    return PositionSnapshot(date(2025, 1, 1), 100000, {})


def _bars(
    symbol: str,
    *,
    days: int,
    start_price: float,
    step: float,
    amount: float = 20_000_000,
    force_limit_up: bool = False,
) -> list[Bar]:
    rows: list[Bar] = []
    start = date(2025, 1, 1)
    price = start_price
    for idx in range(days):
        price = max(1.0, price + step)
        trade_date = start + timedelta(days=idx)
        limit_up = price if force_limit_up and idx == days - 1 else price * 1.10
        rows.append(
            Bar(
                symbol=symbol,
                trade_date=trade_date,
                open=price * 0.99,
                high=price * 1.02,
                low=price * 0.98,
                close=price,
                volume=amount / price,
                amount=amount,
                limit_up=limit_up,
                limit_down=price * 0.90,
            )
        )
    return rows


if __name__ == "__main__":
    unittest.main()
