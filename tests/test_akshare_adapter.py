import unittest
from datetime import date

from quant_system.data.akshare_adapter import _frame_to_bars


class FakeFrame:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        self.assert_orient = orient
        return self.records


class AkshareAdapterTest(unittest.TestCase):
    def test_parses_akshare_chinese_columns(self) -> None:
        frame = FakeFrame(
            [
                {
                    "\u65e5\u671f": "2025-01-02",
                    "\u5f00\u76d8": 4.0,
                    "\u6700\u9ad8": 4.1,
                    "\u6700\u4f4e": 3.9,
                    "\u6536\u76d8": 4.05,
                    "\u6210\u4ea4\u91cf": 100000,
                    "\u6210\u4ea4\u989d": 405000.0,
                }
            ]
        )
        bars = _frame_to_bars("510300", frame)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].trade_date, date(2025, 1, 2))
        self.assertEqual(bars[0].close, 4.05)
        self.assertEqual(bars[0].amount, 405000.0)

    def test_missing_column_error_is_explicit(self) -> None:
        frame = FakeFrame([{"date": "2025-01-02", "open": 4.0}])
        with self.assertRaisesRegex(KeyError, "missing expected column"):
            _frame_to_bars("510300", frame)


if __name__ == "__main__":
    unittest.main()
