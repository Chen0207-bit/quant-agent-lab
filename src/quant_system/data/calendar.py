"""A-share trading calendar backed by AKShare and a local Parquet cache."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class TradingCalendar:
    trading_days: tuple[date, ...]

    def __post_init__(self) -> None:
        days = tuple(sorted(set(self.trading_days)))
        if not days:
            raise ValueError("trading calendar cannot be empty")
        object.__setattr__(self, "trading_days", days)

    @classmethod
    def from_akshare(cls, cache_dir: Path | str, start: date, end: date) -> "TradingCalendar":
        if start > end:
            raise ValueError("calendar start must be <= end")
        path = cls.cache_path(cache_dir)
        days = _read_cached_days(path)
        if not _covers(days, start, end):
            days = _fetch_akshare_days()
            _write_cached_days(path, days)
        calendar = cls(days)
        if not _covers(calendar.trading_days, start, end):
            raise RuntimeError(
                "AKShare trading calendar does not cover "
                f"{start.isoformat()} to {end.isoformat()}"
            )
        return calendar

    @staticmethod
    def cache_path(cache_dir: Path | str) -> Path:
        root = Path(cache_dir)
        return root / "calendar" / "trading_days.parquet"

    def is_trading_day(self, day: date) -> bool:
        idx = bisect_left(self.trading_days, day)
        return idx < len(self.trading_days) and self.trading_days[idx] == day

    def previous_trading_day(self, day: date) -> date:
        idx = bisect_left(self.trading_days, day) - 1
        if idx < 0:
            raise ValueError(f"no previous trading day before {day.isoformat()}")
        return self.trading_days[idx]

    def next_trading_day(self, day: date) -> date:
        idx = bisect_right(self.trading_days, day)
        if idx >= len(self.trading_days):
            raise ValueError(f"no next trading day after {day.isoformat()}")
        return self.trading_days[idx]

    def latest_trading_day(self, end: date) -> date:
        idx = bisect_right(self.trading_days, end) - 1
        if idx < 0:
            raise ValueError(f"no trading day on or before {end.isoformat()}")
        return self.trading_days[idx]


def _read_cached_days(path: Path) -> tuple[date, ...]:
    if not path.exists():
        return ()
    pd = _load_pandas()
    frame = pd.read_parquet(path)
    if "trade_date" not in frame.columns:
        return ()
    return tuple(_parse_day(value) for value in frame["trade_date"].tolist())


def _write_cached_days(path: Path, days: Iterable[date]) -> None:
    pd = _load_pandas()
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [{"trade_date": day.isoformat()} for day in sorted(set(days))]
    pd.DataFrame(records).to_parquet(path, index=False)


def _fetch_akshare_days() -> tuple[date, ...]:
    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("akshare is required to fetch the A-share trading calendar") from exc

    try:
        frame = ak.tool_trade_date_hist_sina()
    except Exception as exc:
        raise RuntimeError(f"failed to fetch AKShare trading calendar: {exc}") from exc

    if "trade_date" not in frame.columns:
        raise RuntimeError("AKShare trading calendar missing trade_date column")
    days = tuple(_parse_day(value) for value in frame["trade_date"].tolist())
    if not days:
        raise RuntimeError("AKShare returned an empty trading calendar")
    return days


def _parse_day(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _covers(days: tuple[date, ...], start: date, end: date) -> bool:
    return bool(days) and min(days) <= start and max(days) >= end


def _load_pandas() -> object:
    try:
        import pandas as pd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pandas/pyarrow are required for trading calendar cache") from exc
    return pd
