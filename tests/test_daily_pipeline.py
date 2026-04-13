import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from quant_system.app.daily_pipeline import run_daily_pipeline
from quant_system.common.models import Bar
from quant_system.data.calendar import TradingCalendar
from quant_system.data.manager import DataManager
from quant_system.data.storage import BarStorage


class FakeDailySource:
    days = (
        date(2025, 1, 2),
        date(2025, 1, 3),
        date(2025, 1, 6),
        date(2025, 1, 7),
        date(2025, 1, 8),
    )

    def fetch_stock_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        return self._bars(symbol, start, end)

    def fetch_etf_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        return self._bars(symbol, start, end)

    def _bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        bars: list[Bar] = []
        price = 4.0 if symbol.startswith(("51", "15")) else 10.0
        for idx, trade_date in enumerate(self.days):
            if start <= trade_date <= end:
                close = price + idx * 0.05
                bars.append(
                    Bar(
                        symbol=symbol,
                        trade_date=trade_date,
                        open=close,
                        high=close * 1.01,
                        low=close * 0.99,
                        close=close,
                        volume=1000000,
                        amount=close * 1000000,
                        limit_up=close * 1.10,
                        limit_down=close * 0.90,
                    )
                )
        return bars


class DailyPipelineTest(unittest.TestCase):
    def test_pipeline_writes_reports_from_fake_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager = DataManager(
                storage=BarStorage(root / "data"),
                source=FakeDailySource(),
                max_retries=1,
                retry_backoff_seconds=0,
            )
            result = run_daily_pipeline(
                as_of=date(2025, 1, 8),
                start=date(2025, 1, 2),
                config_dir=Path("configs"),
                data_dir=root / "data",
                report_dir=root / "reports",
                symbols=("510300",),
                lookback_days=2,
                calendar=TradingCalendar(FakeDailySource.days),
                data_manager=manager,
            )

            self.assertEqual(result.as_of, date(2025, 1, 8))
            summary_path = result.report_dir / "daily_summary.md"
            json_path = result.report_dir / "daily_summary.json"
            manual_path = result.report_dir / "manual_orders.csv"
            sync_path = result.report_dir / "data_sync_report.json"
            diagnostics_path = result.report_dir / "strategy_diagnostics.json"
            self.assertTrue(summary_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(manual_path.exists())
            self.assertTrue(sync_path.exists())
            self.assertTrue(diagnostics_path.exists())
            self.assertIn("Daily Agent Summary", summary_path.read_text(encoding="utf-8"))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["as_of"], "2025-01-08")
            self.assertEqual(payload["symbols"], ["510300"])
            self.assertTrue(payload["data_sync"]["quality_passed"])
            self.assertIn("strategy_diagnostics_path", payload)
            self.assertIn("raw_candidate_counts", payload)
            diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["meta_decision"]["mode"], "defensive_hold")
            self.assertIn("records", diagnostics)
            self.assertIn("order_id", manual_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
