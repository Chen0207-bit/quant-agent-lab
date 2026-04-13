import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path

from quant_system.common.models import Bar
from quant_system.data.manager import DataManager
from quant_system.data.storage import BarStorage


HAS_PARQUET_DEPS = importlib.util.find_spec("pandas") is not None and importlib.util.find_spec("pyarrow") is not None


class FlakySource:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_stock_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("temporary")
        return [Bar(symbol, start, 10, 11, 9, 10, 1000)]

    def fetch_etf_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        return self.fetch_stock_daily(symbol, start, end)


class DataManagerTest(unittest.TestCase):
    def test_sync_retries_temporary_source_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = FlakySource()
            manager = DataManager(storage=BarStorage(Path(tmpdir)), source=source, max_retries=2, retry_backoff_seconds=0)
            report = manager.sync_history(["600000"], date(2025, 1, 2), date(2025, 1, 3))
            self.assertTrue(report.quality_passed)
            self.assertEqual(source.calls, 2)

    @unittest.skipUnless(HAS_PARQUET_DEPS, "pandas/pyarrow not installed")
    def test_parquet_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = BarStorage(Path(tmpdir))
            bars = [
                Bar("510300", date(2025, 1, 2), 4.0, 4.1, 3.9, 4.05, 100000, amount=405000),
                Bar("510300", date(2025, 1, 3), 4.1, 4.2, 4.0, 4.15, 110000, amount=456500),
            ]
            storage.write_bars("silver", bars)
            manager = DataManager(storage=storage)
            loaded = manager.get_history("510300", start_date=date(2025, 1, 2), end_date=date(2025, 1, 3))
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[-1].close, 4.15)
            if importlib.util.find_spec("duckdb") is not None:
                connection = storage.register_duckdb_view("silver")
                self.assertEqual(connection.execute("select count(*) from bars").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
