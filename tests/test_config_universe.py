import unittest
from datetime import date

from quant_system.common.models import Bar, Board
from quant_system.config.settings import UniverseBucketConfig, UniverseConfig, UniverseSymbolMetadata, load_universe_config
from quant_system.data.universe import build_mvp_universe, build_universe_snapshot


class ConfigUniverseTest(unittest.TestCase):
    def test_load_universe_config_reads_sample_symbols(self) -> None:
        config = load_universe_config("configs/universe.toml")
        self.assertEqual(config.initial_cash_cny, 100000)
        self.assertEqual(config.etf_long.symbols, ("510300", "510500", "159915"))
        self.assertIn("600000", config.main_board_short.symbols)
        self.assertIn("002415", config.main_board_short.symbols)

    def test_build_mvp_universe_includes_etf_and_main_board_samples(self) -> None:
        config = load_universe_config("configs/universe.toml")
        universe = build_mvp_universe(config)
        self.assertEqual(universe["510300"].board, Board.ETF)
        self.assertEqual(universe["600000"].board, Board.MAIN)
        self.assertEqual(universe["000001"].board, Board.MAIN)


    def test_build_universe_snapshot_uses_metadata_and_liquidity(self) -> None:
        config = UniverseConfig(
            market="cn_a_share",
            frequency="daily",
            initial_cash_cny=100000,
            etf_long=UniverseBucketConfig(enabled=True, symbols=("510300",)),
            main_board_short=UniverseBucketConfig(enabled=True, symbols=("600000",)),
            symbol_metadata={
                "600000": UniverseSymbolMetadata(
                    industry="bank",
                    style_tags=("large_cap", "value"),
                    free_float_mkt_cap=500000000000.0,
                    fundamentals={"roe": 0.12},
                )
            },
        )
        universe = build_mvp_universe(config)
        bar = Bar(
            "600000",
            date(2025, 1, 2),
            open=10.0,
            high=10.2,
            low=9.8,
            close=10.1,
            volume=1000000,
            amount=10100000.0,
        )
        snapshot = build_universe_snapshot(date(2025, 1, 2), universe, {"600000": bar}, config)

        member = snapshot.members["600000"]
        self.assertEqual(member.industry, "bank")
        self.assertEqual(member.style_tags, ("large_cap", "value"))
        self.assertEqual(member.liquidity_cny, 10100000.0)
        self.assertEqual(member.fundamentals["roe"], 0.12)

    def test_build_mvp_universe_filters_disallowed_prefixes_and_unknowns(self) -> None:
        config = UniverseConfig(
            market="cn_a_share",
            frequency="daily",
            initial_cash_cny=100000,
            etf_long=UniverseBucketConfig(enabled=True, symbols=("510300",)),
            main_board_short=UniverseBucketConfig(
                enabled=True,
                symbols=("600000", "300001", "688001", "830000", "400001", "999999", "000001"),
                exclude_prefixes=("300", "301", "688", "689", "8", "4"),
            ),
        )
        universe = build_mvp_universe(config)
        self.assertIn("510300", universe)
        self.assertIn("600000", universe)
        self.assertIn("000001", universe)
        self.assertNotIn("300001", universe)
        self.assertNotIn("688001", universe)
        self.assertNotIn("830000", universe)
        self.assertNotIn("400001", universe)
        self.assertNotIn("999999", universe)


if __name__ == "__main__":
    unittest.main()
