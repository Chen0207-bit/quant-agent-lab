"""Run the daily A-share paper pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from quant_system.app.daily_pipeline import DailyPipelineError, run_daily_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily A-share paper pipeline.")
    parser.add_argument("--as-of", help="Calendar date, YYYY-MM-DD. Non-trading dates roll back.")
    parser.add_argument("--start", help="Optional sync start date, YYYY-MM-DD")
    parser.add_argument("--symbols", help="Comma-separated symbols. Defaults to configs/universe.toml.")
    parser.add_argument("--config-dir", default="configs", help="Configuration directory")
    parser.add_argument("--data-dir", default="runs/data", help="Local data directory")
    parser.add_argument("--report-dir", default="runs/reports", help="Report output directory")
    parser.add_argument("--dataset", default="silver", choices=["silver", "gold"], help="Dataset to read/write")
    parser.add_argument("--lookback-days", type=int, help="Override strategy lookback days")
    parser.add_argument("--max-retries", type=int, default=3, help="Fetch retries per symbol")
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0, help="Seconds between retries")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()) if args.symbols else None
    try:
        result = run_daily_pipeline(
            as_of=_parse_date(args.as_of) if args.as_of else None,
            start=_parse_date(args.start) if args.start else None,
            config_dir=Path(args.config_dir),
            data_dir=Path(args.data_dir),
            report_dir=Path(args.report_dir),
            symbols=symbols,
            dataset=args.dataset,
            lookback_days=args.lookback_days,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )
    except DailyPipelineError as exc:
        print(f"daily_pipeline failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(
        json.dumps(
            {
                "as_of": result.as_of.isoformat(),
                "symbols": list(result.symbols),
                "report_dir": str(result.report_dir),
                "bars_written": result.data_sync_report.bars_written,
                "quality_passed": result.data_sync_report.quality_passed,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    main()
