import unittest
from datetime import date

from quant_system.agents.regime_agent import RegimeState
from quant_system.agents.signal_agent import SignalAgent
from quant_system.common.models import Bar, PositionSnapshot, TargetPosition


class DummyStrategy:
    strategy_id = "etf_momentum"

    def generate_targets(self, as_of: date, history: dict[str, list[Bar]], portfolio: PositionSnapshot) -> list[TargetPosition]:
        return [TargetPosition("510300", 0.5, "dummy")]


class SignalAgentTest(unittest.TestCase):
    def test_regime_weight_scales_target(self) -> None:
        agent = SignalAgent([DummyStrategy()])
        regime = RegimeState("trending", 0.7, {"etf_momentum": 0.7, "default": 0.1}, "test")
        targets = agent.generate_targets(date(2025, 1, 2), {}, PositionSnapshot(date(2025, 1, 2), 100000, {}), regime)
        self.assertEqual(len(targets), 1)
        self.assertAlmostEqual(targets[0].target_weight, 0.35)


if __name__ == "__main__":
    unittest.main()
