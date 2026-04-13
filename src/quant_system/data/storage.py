"""Parquet and DuckDB storage helpers for daily bars."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Sequence
import re

from quant_system.common.models import Bar

VALID_DATASETS = {"raw", "silver", "gold"}


class BarStorage:
    def __init__(self, base_dir: Path | str = Path("runs/data")) -> None:
        self.base_dir = Path(base_dir)

    def dataset_dir(self, dataset: str) -> Path:
        _validate_dataset(dataset)
        return self.base_dir / dataset

    def symbol_path(self, dataset: str, symbol: str, partition: str | None = None) -> Path:
        _validate_dataset(dataset)
        suffix = f"_{partition}" if partition else ""
        return self.dataset_dir(dataset) / f"{symbol}{suffix}.parquet"

    def write_bars(self, dataset: str, bars: Sequence[Bar], partition: str | None = None) -> Path:
        if not bars:
            raise ValueError("cannot write empty bars")
        symbol = bars[0].symbol
        if any(bar.symbol != symbol for bar in bars):
            raise ValueError("write_bars expects one symbol per file")
        pd = _load_pandas()
        path = self.symbol_path(dataset, symbol, partition)
        path.parent.mkdir(parents=True, exist_ok=True)
        records = [_bar_to_record(bar) for bar in sorted(bars, key=lambda item: item.trade_date)]
        pd.DataFrame(records).to_parquet(path, index=False)
        return path

    def read_bars(
        self,
        dataset: str,
        symbols: Sequence[str],
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, list[Bar]]:
        pd = _load_pandas()
        result: dict[str, list[Bar]] = {}
        for symbol in symbols:
            path = self.symbol_path(dataset, symbol)
            if not path.exists():
                result[symbol] = []
                continue
            frame = pd.read_parquet(path)
            rows = frame.to_dict("records")
            bars = [_record_to_bar(row) for row in rows]
            result[symbol] = [
                bar
                for bar in bars
                if (start is None or bar.trade_date >= start) and (end is None or bar.trade_date <= end)
            ]
        return result

    def register_duckdb_view(self, dataset: str, view_name: str = "bars") -> object:
        duckdb = _load_duckdb()
        _validate_identifier(view_name)
        pattern = str(self.dataset_dir(dataset) / "*.parquet").replace("'", "''")
        connection = duckdb.connect()
        connection.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{pattern}')")
        return connection


def write_bars(dataset: str, bars: Sequence[Bar], partition: str | None = None) -> Path:
    return BarStorage().write_bars(dataset, bars, partition)


def read_bars(
    symbols: Sequence[str],
    start: date | None = None,
    end: date | None = None,
    dataset: str = "silver",
) -> dict[str, list[Bar]]:
    return BarStorage().read_bars(dataset, symbols, start, end)


def register_duckdb_view(dataset: str, view_name: str = "bars") -> object:
    return BarStorage().register_duckdb_view(dataset, view_name)


def _validate_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("view_name must be a simple SQL identifier")


def _validate_dataset(dataset: str) -> None:
    if dataset not in VALID_DATASETS:
        raise ValueError(f"dataset must be one of {sorted(VALID_DATASETS)}")


def _bar_to_record(bar: Bar) -> dict[str, object]:
    record = asdict(bar)
    record["trade_date"] = bar.trade_date.isoformat()
    return record


def _record_to_bar(row: dict[str, object]) -> Bar:
    trade_date = row["trade_date"]
    if isinstance(trade_date, datetime):
        parsed_date = trade_date.date()
    elif isinstance(trade_date, date):
        parsed_date = trade_date
    else:
        parsed_date = datetime.strptime(str(trade_date), "%Y-%m-%d").date()
    return Bar(
        symbol=str(row["symbol"]),
        trade_date=parsed_date,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        amount=float(row.get("amount", 0.0) or 0.0),
        pre_close=_optional_float(row.get("pre_close")),
        limit_up=_optional_float(row.get("limit_up")),
        limit_down=_optional_float(row.get("limit_down")),
        is_suspended=bool(row.get("is_suspended", False)),
    )


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        if str(value).lower() == "nan":
            return None
    except Exception:
        pass
    return float(value)


def _load_pandas() -> object:
    try:
        import pandas as pd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pandas/pyarrow are required for Parquet storage. Install project dependencies.") from exc
    return pd


def _load_duckdb() -> object:
    try:
        import duckdb  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("duckdb is required for DuckDB views. Install project dependencies.") from exc
    return duckdb
