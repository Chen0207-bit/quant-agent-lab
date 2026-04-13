"""Domain models shared across the quant system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum


class Exchange(StrEnum):
    SSE = "SSE"
    SZSE = "SZSE"
    BSE = "BSE"
    UNKNOWN = "UNKNOWN"


class Board(StrEnum):
    MAIN = "MAIN"
    ETF = "ETF"
    CHINEXT = "CHINEXT"
    STAR = "STAR"
    BSE = "BSE"
    UNKNOWN = "UNKNOWN"


class AssetType(StrEnum):
    STOCK = "STOCK"
    ETF = "ETF"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    NEW = "NEW"
    ACK = "ACK"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class RiskAction(StrEnum):
    APPROVE = "APPROVE"
    REDUCE = "REDUCE"
    REJECT = "REJECT"
    LIQUIDATE_ONLY = "LIQUIDATE_ONLY"


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    name: str
    exchange: Exchange
    board: Board
    asset_type: AssetType
    lot_size: int = 100
    price_limit_pct: float = 0.10
    is_st: bool = False
    is_suspended: bool = False


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0
    pre_close: float | None = None
    limit_up: float | None = None
    limit_down: float | None = None
    is_suspended: bool = False

    def is_valid_ohlc(self) -> bool:
        if min(self.open, self.high, self.low, self.close) <= 0:
            return False
        return self.high >= max(self.open, self.close, self.low) and self.low <= min(
            self.open, self.close, self.high
        )


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    symbol: str
    as_of: date
    values: dict[str, float]


@dataclass(frozen=True, slots=True)
class Signal:
    signal_id: str
    strategy_id: str
    symbol: str
    side: Side
    strength: float
    horizon_days: int
    confidence: float
    reason: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class TargetPosition:
    symbol: str
    target_weight: float
    reason: str


@dataclass(frozen=True, slots=True)
class StrategyDiagnosticRecord:
    as_of: date
    strategy_id: str
    symbol: str
    eligible: bool
    selected: bool
    score: float | None
    raw_features: dict[str, float]
    target_weight: float
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class OrderIntent:
    order_id: str
    strategy_id: str
    signal_id: str | None
    symbol: str
    side: Side
    qty: int
    limit_price: float | None
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class Order:
    order_id: str
    strategy_id: str
    signal_id: str | None
    symbol: str
    side: Side
    qty: int
    limit_price: float | None
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    reject_reason: str | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: Side
    qty: int
    price: float
    commission: float
    stamp_tax: float
    transfer_fee: float
    slippage: float
    timestamp: datetime

    @property
    def notional(self) -> float:
        return self.qty * self.price


@dataclass(slots=True)
class Position:
    symbol: str
    qty: int = 0
    available_qty: int = 0
    avg_cost: float = 0.0
    market_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.qty * self.market_price


@dataclass(slots=True)
class PositionSnapshot:
    as_of: date
    cash: float
    positions: dict[str, Position]

    @property
    def equity(self) -> float:
        return self.cash + sum(position.market_value for position in self.positions.values())


@dataclass(frozen=True, slots=True)
class RiskRejection:
    order_id: str
    symbol: str
    reason: str


@dataclass(frozen=True, slots=True)
class RiskDecision:
    action: RiskAction
    approved_orders: tuple[OrderIntent, ...]
    rejections: tuple[RiskRejection, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    as_of: date
    cash: float
    positions_count: int
    open_orders_count: int
    is_consistent: bool
    issues: tuple[str, ...]
