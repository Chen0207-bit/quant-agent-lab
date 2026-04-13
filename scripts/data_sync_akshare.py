"""Sync A-share daily data from AKShare into local Parquet storage."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from quant_system.data.manager import DataManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync A-share daily data from AKShare.")
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. 510300,510500")
    parser.add_argument("--data-dir", default="runs/data", help="Local data directory")
    parser.add_argument("--dataset", default="silver", choices=["silver", "gold"], help="Derived dataset to write")
    parser.add_argument("--max-retries", type=int, default=3, help="Fetch retries per symbol")
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0, help="Seconds between retries")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    if not symbols:
        raise SystemExit("--symbols must contain at least one symbol")
    manager = DataManager(data_dir=Path(args.data_dir), max_retries=args.max_retries, retry_backoff_seconds=args.retry_backoff_seconds)
    report = manager.sync_history(symbols, start, end, dataset=args.dataset)
    print(json.dumps(asdict(report), ensure_ascii=True, indent=2, sort_keys=True))
    if not report.quality_passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
