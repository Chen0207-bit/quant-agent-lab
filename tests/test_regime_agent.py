import unittest
from datetime import date, timedelta

from quant_system.agents.regime_agent import RegimeAgent
from quant_system.common.models import Bar


class RegimeAgentTest(unittest.TestCase):
    def test_detects_trending(self) -> None:
        history = {"510300": _bars_from_returns("510300", [0.001] * 30)}
        regime = RegimeAgent().detect(history)
        self.assertEqual(regime.regime, "trending")
        self.assertGreater(regime.weights["etf_momentum"], regime.weights["main_board_breakout"])

    def test_detects_mean_reverting(self) -> None:
        returns = [0.0005, -0.0005] * 20
        regime = RegimeAgent().detect({"510300": _bars_from_returns("510300", returns)})
        self.assertEqual(regime.regime, "mean_reverting")

    def test_detects_crisis(self) -> None:
        returns = [0.05, -0.04] * 20
        history = {
            "510300": _bars_from_returns("510300", returns),
            "510500": _bars_from_returns("510500", returns),
        }
        regime = RegimeAgent().detect(history)
        self.assertEqual(regime.regime, "crisis")
        self.assertGreater(regime.weights["defensive"], 0.5)


    def test_conflicting_trend_and_high_vol_is_uncertain(self) -> None:
        returns = [0.06, -0.02, 0.05, -0.01] * 10
        regime = RegimeAgent().detect({"510300": _bars_from_returns("510300", returns)})
        self.assertEqual(regime.regime, "uncertain")

    def test_detects_uncertain_on_insufficient_history(self) -> None:
        regime = RegimeAgent().detect({"510300": _bars_from_returns("510300", [0.01])})
        self.assertEqual(regime.regime, "uncertain")


def _bars_from_returns(symbol: str, returns: list[float]) -> list[Bar]:
    price = 10.0
    start = date(2025, 1, 1)
    bars = [_bar(symbol, start, price)]
    for idx, ret in enumerate(returns, start=1):
        price *= 1 + ret
        bars.append(_bar(symbol, start + timedelta(days=idx), price))
    return bars


def _bar(symbol: str, trade_date: date, price: float) -> Bar:
    return Bar(symbol, trade_date, price, price * 1.01, price * 0.99, price, 1000000, limit_up=price * 1.1, limit_down=price * 0.9)


if __name__ == "__main__":
    unittest.main()
