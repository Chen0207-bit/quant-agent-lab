"""Optional AKShare adapter.

The core system does not import AKShare at module import time. Tests stay offline,
and deployment decides when to install or update the provider package.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from quant_system.common.models import Bar

DATE_COL = "\u65e5\u671f"
OPEN_COL = "\u5f00\u76d8"
HIGH_COL = "\u6700\u9ad8"
LOW_COL = "\u6700\u4f4e"
CLOSE_COL = "\u6536\u76d8"
VOLUME_COL = "\u6210\u4ea4\u91cf"
AMOUNT_COL = "\u6210\u4ea4\u989d"


class AkshareDailyDataSource:
    def __init__(self, adjust: str = "qfq") -> None:
        self.adjust = adjust

    def fetch_stock_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        ak = _load_akshare()
        try:
            frame = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust=self.adjust,
            )
            return _frame_to_bars(symbol, frame)
        except Exception:
            frame = ak.stock_zh_a_hist_tx(
                symbol=_prefixed_market_symbol(symbol),
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust=self.adjust,
            )
            return _filter_bars(_frame_to_bars(symbol, frame), start, end)

    def fetch_etf_daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        ak = _load_akshare()
        try:
            frame = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust=self.adjust,
            )
            return _frame_to_bars(symbol, frame)
        except Exception:
            frame = ak.fund_etf_hist_sina(symbol=_prefixed_market_symbol(symbol))
            return _filter_bars(_frame_to_bars(symbol, frame), start, end)


def _prefixed_market_symbol(symbol: str) -> str:
    clean = symbol.split(".")[0]
    if clean.startswith(("5", "6")):
        return f"sh{clean}"
    return f"sz{clean}"


def _filter_bars(bars: list[Bar], start: date, end: date) -> list[Bar]:
    return [bar for bar in bars if start <= bar.trade_date <= end]


def _load_akshare() -> Any:
    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("AKShare is not installed. Install project dependencies first.") from exc
    return ak


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _field(row: dict[str, Any], *candidates: str, default: Any | None = None) -> Any:
    for candidate in candidates:
        if candidate in row:
            return row[candidate]
    if default is not None:
        return default
    available = ", ".join(sorted(str(key) for key in row))
    expected = ", ".join(candidates)
    raise KeyError(f"AKShare frame missing expected column(s): {expected}; available: {available}")


def _frame_to_bars(symbol: str, frame: Any) -> list[Bar]:
    bars: list[Bar] = []
    for row in frame.to_dict("records"):
        bars.append(
            Bar(
                symbol=symbol,
                trade_date=_to_date(_field(row, DATE_COL, "date", "trade_date")),
                open=float(_field(row, OPEN_COL, "open")),
                high=float(_field(row, HIGH_COL, "high")),
                low=float(_field(row, LOW_COL, "low")),
                close=float(_field(row, CLOSE_COL, "close")),
                volume=float(_field(row, VOLUME_COL, "volume", default=0.0)),
                amount=float(_field(row, AMOUNT_COL, "amount", default=0.0)),
            )
        )
    return bars
