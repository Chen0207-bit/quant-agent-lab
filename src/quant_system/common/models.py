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
class UniverseMember:
    symbol: str
    board: str
    asset_type: str
    industry: str = "unknown"
    liquidity_cny: float = 0.0
    free_float_mkt_cap: float | None = None
    is_st: bool = False
    is_suspended: bool = False
    price_limit_pct: float = 0.10
    style_tags: tuple[str, ...] = ()
    fundamentals: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    as_of: date
    members: dict[str, UniverseMember]


@dataclass(frozen=True, slots=True)
class PortfolioConstraints:
    max_position_weight: float = 0.20
    max_industry_weight: float = 0.35
    turnover_budget: float = 0.50
    min_cash_buffer_pct: float = 0.05
    min_lot_size: int = 100


@dataclass(frozen=True, slots=True)
class StrategyContext:
    as_of: date
    universe_snapshot: UniverseSnapshot | None = None
    regime_name: str = "default"
    portfolio_constraints: PortfolioConstraints = field(default_factory=PortfolioConstraints)
    rebalance_frequency: str = "daily"
    sleeve_budget: float = 1.0


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    strategy_id: str
    family: str
    symbol: str
    score: float | None
    eligible: bool
    selected: bool
    rank: int | None
    rank_percentile: float | None
    peer_distance: float | None
    raw_features: dict[str, float]
    universe_size: int = 0
    normalized_features: dict[str, float] = field(default_factory=dict)
    target_weight: float = 0.0
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class StrategyDiagnosticRecord:
    as_of: date
    strategy_id: str
    family: str
    symbol: str
    eligible: bool
    selected: bool
    score: float | None
    rank: int | None = None
    rank_percentile: float | None = None
    universe_size: int = 0
    peer_distance: float | None = None
    raw_features: dict[str, float] = field(default_factory=dict)
    normalized_features: dict[str, float] = field(default_factory=dict)
    target_weight: float = 0.0
    target_weight_before_regime: float = 0.0
    target_weight_after_regime: float = 0.0
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
    equity: float
    unrealized_pnl: float
    is_consistent: bool
    reasons: tuple[str, ...] = ()
