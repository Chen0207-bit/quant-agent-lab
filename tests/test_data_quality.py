import unittest
from datetime import date

from quant_system.common.models import Bar
from quant_system.data.quality import validate_bars


class DataQualityTest(unittest.TestCase):
    def test_rejects_duplicate_and_invalid_ohlc(self) -> None:
        bar = Bar("600000", date(2025, 1, 2), open=10, high=11, low=9, close=10, volume=1000)
        bad = Bar("600000", date(2025, 1, 3), open=10, high=9, low=8, close=10, volume=1000)
        report = validate_bars([bar, bar, bad])
        self.assertFalse(report.passed)
        self.assertTrue(any(issue.message == "duplicate bar" for issue in report.issues))
        self.assertTrue(any(issue.message == "invalid ohlc values" for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
