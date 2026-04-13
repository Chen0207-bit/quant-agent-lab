import unittest
from datetime import date

from quant_system.data.calendar import TradingCalendar


class TradingCalendarTest(unittest.TestCase):
    def setUp(self) -> None:
        self.calendar = TradingCalendar(
            (
                date(2025, 1, 2),
                date(2025, 1, 3),
                date(2025, 1, 6),
                date(2025, 1, 7),
            )
        )

    def test_is_trading_day(self) -> None:
        self.assertTrue(self.calendar.is_trading_day(date(2025, 1, 3)))
        self.assertFalse(self.calendar.is_trading_day(date(2025, 1, 4)))

    def test_previous_next_and_latest(self) -> None:
        self.assertEqual(self.calendar.previous_trading_day(date(2025, 1, 6)), date(2025, 1, 3))
        self.assertEqual(self.calendar.next_trading_day(date(2025, 1, 3)), date(2025, 1, 6))
        self.assertEqual(self.calendar.latest_trading_day(date(2025, 1, 5)), date(2025, 1, 3))
        self.assertEqual(self.calendar.latest_trading_day(date(2025, 1, 6)), date(2025, 1, 6))

    def test_edges_raise_explicitly(self) -> None:
        with self.assertRaises(ValueError):
            self.calendar.previous_trading_day(date(2025, 1, 2))
        with self.assertRaises(ValueError):
            self.calendar.latest_trading_day(date(2025, 1, 1))
        with self.assertRaises(ValueError):
            self.calendar.next_trading_day(date(2025, 1, 7))


if __name__ == "__main__":
    unittest.main()
