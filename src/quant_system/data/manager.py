"""Data manager for A-share daily bars."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from time import sleep
from typing import Protocol, Sequence

from quant_system.common.models import Bar, Board
from quant_system.data.akshare_adapter import AkshareDailyDataSource
from quant_system.data.a_share_rules import classify_symbol
from quant_system.data.quality import DataQualityIssue, DataQualityReport, validate_bars
from quant_system.data.storage import BarStorage


@dataclass(frozen=True, slots=True)
class DataSyncReport:
    symbols_requested: tuple[str, ...]
    symbols_succeeded: tuple[str, ...]
    symbols_failed: tuple[str, ...]
    bars_written: int
    quality_passed: bool
    issues: tuple[str, ...] = field(default_factory=tuple)


class DailyDataSource(Protocol):
    def fetch_stock_daily(self, symbol: str, start: date, end: date) -> list[Bar]: ...

    def fetch_etf_daily(self, symbol: str, start: date, end: date) -> list[Bar]: ...


class DataManager:
    def __init__(
        self,
        storage: BarStorage | None = None,
        source: DailyDataSource | None = None,
        data_dir: Path | str = Path("runs/data"),
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.storage = storage or BarStorage(data_dir)
        self.source = source or AkshareDailyDataSource()
        self.max_retries = max(1, max_retries)
        self.retry_backoff_seconds = retry_backoff_seconds

    def get_history(
        self,
        symbol: str,
        days: int | None = None,
        end_date: date | None = None,
        start_date: date | None = None,
        dataset: str = "silver",
    ) -> list[Bar]:
        bars = self.storage.read_bars(dataset, [symbol], start=start_date, end=end_date).get(symbol, [])
        if days is not None:
            return bars[-days:]
        return bars

    def get_latest(self, symbols: Sequence[str], dataset: str = "silver") -> dict[str, Bar]:
        latest: dict[str, Bar] = {}
        history = self.storage.read_bars(dataset, symbols)
        for symbol, bars in history.items():
            if bars:
                latest[symbol] = bars[-1]
        return latest

    def validate(self, bars: list[Bar]) -> DataQualityReport:
        return validate_bars(bars)

    def sync_history(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        dataset: str = "silver",
    ) -> DataSyncReport:
        succeeded: list[str] = []
        failed: list[str] = []
        issues: list[str] = []
        bars_written = 0

        for symbol in symbols:
            try:
                bars = self._fetch_with_retries(symbol, start, end)
                report = validate_bars(bars)
                if not report.passed:
                    failed.append(symbol)
                    issues.extend(_format_quality_issue(issue) for issue in report.issues)
                    continue
                if bars:
                    self.storage.write_bars("raw", bars)
                    self.storage.write_bars(dataset, bars)
                    bars_written += len(bars)
                    succeeded.append(symbol)
                else:
                    failed.append(symbol)
                    issues.append(f"{symbol}: no bars returned")
            except Exception as exc:
                failed.append(symbol)
                issues.append(f"{symbol}: {type(exc).__name__}: {exc}")

        return DataSyncReport(
            symbols_requested=tuple(symbols),
            symbols_succeeded=tuple(succeeded),
            symbols_failed=tuple(failed),
            bars_written=bars_written,
            quality_passed=not failed,
            issues=tuple(issues),
        )

    def _fetch_with_retries(self, symbol: str, start: date, end: date) -> list[Bar]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._fetch_symbol(symbol, start, end)
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries and self.retry_backoff_seconds > 0:
                    sleep(self.retry_backoff_seconds)
        assert last_error is not None
        raise last_error

    def _fetch_symbol(self, symbol: str, start: date, end: date) -> list[Bar]:
        instrument = classify_symbol(symbol)
        if instrument.board == Board.ETF:
            return self.source.fetch_etf_daily(symbol, start, end)
        return self.source.fetch_stock_daily(symbol, start, end)


def _format_quality_issue(issue: DataQualityIssue) -> str:
    return f"{issue.symbol}@{issue.trade_date} {issue.severity}: {issue.message}"
