import unittest

from quant_system.common.models import Board, Side
from quant_system.data.a_share_rules import classify_symbol, round_to_lot, would_cross_price_limit


class AShareRulesTest(unittest.TestCase):
    def test_classifies_allowed_main_board_and_excluded_boards(self) -> None:
        self.assertEqual(classify_symbol("600000").board, Board.MAIN)
        self.assertEqual(classify_symbol("000001").board, Board.MAIN)
        self.assertEqual(classify_symbol("510300").board, Board.ETF)
        self.assertEqual(classify_symbol("300750").board, Board.CHINEXT)
        self.assertEqual(classify_symbol("688001").board, Board.STAR)

    def test_round_to_lot(self) -> None:
        self.assertEqual(round_to_lot(99), 0)
        self.assertEqual(round_to_lot(100), 100)
        self.assertEqual(round_to_lot(230), 200)

    def test_price_limit_blocking(self) -> None:
        self.assertTrue(would_cross_price_limit(Side.BUY, 11.0, 11.0, 9.0))
        self.assertTrue(would_cross_price_limit(Side.SELL, 9.0, 11.0, 9.0))
        self.assertFalse(would_cross_price_limit(Side.BUY, 10.9, 11.0, 9.0))


if __name__ == "__main__":
    unittest.main()
