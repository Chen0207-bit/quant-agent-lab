"""Baseline strategies for the A-share MVP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from quant_system.common.models import (
    Bar,
    Board,
    PositionSnapshot,
    ScoredCandidate,
    StrategyContext,
    StrategyDiagnosticRecord,
    TargetPosition,
)
from quant_system.data.a_share_rules import classify_symbol
from quant_system.features.factors import (
    annualized_volatility,
    breakout_score,
    is_limit_up_buy_blocked,
    momentum,
    moving_average,
    traded_amount,
    weighted_momentum,
)


@dataclass(frozen=True, slots=True)
class EtfMomentumStrategy:
    strategy_id: str
    symbols: tuple[str, ...]
    lookback_days: int = 20
    top_n: int = 2
    min_momentum: float = 0.0
    max_weight_per_symbol: float = 0.25
    lookback_windows: tuple[int, ...] = ()
    window_weights: tuple[float, ...] = ()
    volatility_window: int = 60
    volatility_penalty: float = 0.25
    family: str = "etf"
    rebalance_frequency: str = "daily"

    def generate_targets(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[TargetPosition]:
        diagnostics = self.diagnose(as_of, history, portfolio)
        selected = [record for record in diagnostics if record.selected]
        return [
            TargetPosition(
                symbol=record.symbol,
                target_weight=record.target_weight,
                reason=_format_etf_reason(record),
            )
            for record in selected
        ]

    def rank_candidates(
        self,
        context: StrategyContext,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[ScoredCandidate]:
        diagnostics = self.diagnose(context.as_of, history, portfolio, context)
        return [_diagnostic_to_candidate(record) for record in diagnostics]

    def diagnose(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
        context: StrategyContext | None = None,
    ) -> list[StrategyDiagnosticRecord]:
        del portfolio, context
        preliminary: list[StrategyDiagnosticRecord] = []
        for symbol in self.symbols:
            score, raw_features, rejection_reason = self._score_symbol(history.get(symbol, []))
            eligible = rejection_reason is None and score is not None and score >= self.min_momentum
            if rejection_reason is None and score is not None and score < self.min_momentum:
                rejection_reason = "score_below_min_momentum"
            preliminary.append(
                StrategyDiagnosticRecord(
                    as_of=as_of,
                    strategy_id=self.strategy_id,
                    family=self.family,
                    symbol=symbol,
                    eligible=eligible,
                    selected=False,
                    score=score,
                    raw_features=raw_features,
                    target_weight=0.0,
                    rejection_reason=rejection_reason,
                )
            )

        selected_symbols = {
            record.symbol
            for record in sorted(
                (record for record in preliminary if record.eligible and record.score is not None),
                key=lambda item: item.score,
                reverse=True,
            )[: self.top_n]
        }
        rank_by_symbol, rank_percentile_by_symbol = _rank_eligible(preliminary)
        selected_count = len(selected_symbols)
        selected_weight = min(self.max_weight_per_symbol, 1.0 / selected_count) if selected_count else 0.0
        return [
            StrategyDiagnosticRecord(
                as_of=record.as_of,
                strategy_id=record.strategy_id,
                family=record.family,
                symbol=record.symbol,
                eligible=record.eligible,
                selected=record.symbol in selected_symbols,
                score=record.score,
                rank=rank_by_symbol.get(record.symbol),
                rank_percentile=rank_percentile_by_symbol.get(record.symbol),
                universe_size=len(preliminary),
                raw_features=record.raw_features,
                target_weight=selected_weight if record.symbol in selected_symbols else 0.0,
                target_weight_before_regime=selected_weight if record.symbol in selected_symbols else 0.0,
                target_weight_after_regime=selected_weight if record.symbol in selected_symbols else 0.0,
                rejection_reason=record.rejection_reason,
            )
            for record in preliminary
        ]

    def max_lookback(self) -> int:
        windows = self._effective_windows()
        volatility_window = self._effective_volatility_window()
        return max((*windows, volatility_window))

    def is_rebalance_day(self, as_of: date, history: dict[str, list[Bar]]) -> bool:
        del history
        return _is_configured_rebalance_day(self.rebalance_frequency, as_of)

    def _score_symbol(self, bars: list[Bar]) -> tuple[float | None, dict[str, float], str | None]:
        windows = self._effective_windows()
        weights = self._effective_weights(windows)
        raw_features: dict[str, float] = {}
        if len(bars) <= max(windows):
            return None, raw_features, f"insufficient_history_for_window_{max(windows)}"

        momentum_values: list[float] = []
        for window in windows:
            value = momentum(bars, window)
            if value is None:
                return None, raw_features, f"insufficient_history_for_window_{window}"
            raw_features[f"momentum_{window}"] = value
            momentum_values.append(value)

        weighted = weighted_momentum(bars, windows, weights)
        if weighted is None:
            return None, raw_features, "weighted_momentum_unavailable"
        raw_features["weighted_momentum"] = weighted

        volatility_window = self._effective_volatility_window()
        volatility = annualized_volatility(bars, volatility_window)
        if volatility is None:
            return None, raw_features, f"insufficient_history_for_volatility_{volatility_window}"
        raw_features[f"annualized_volatility_{volatility_window}"] = volatility

        score = weighted - self.volatility_penalty * volatility
        raw_features["volatility_penalty"] = self.volatility_penalty
        raw_features["score"] = score
        return score, raw_features, None

    def _effective_windows(self) -> tuple[int, ...]:
        windows = tuple(int(window) for window in self.lookback_windows if int(window) > 0)
        return windows or (self.lookback_days,)

    def _effective_weights(self, windows: Sequence[int]) -> tuple[float, ...]:
        raw = tuple(float(weight) for weight in self.window_weights)
        if len(raw) != len(windows) or sum(raw) <= 0:
            return tuple(1.0 / len(windows) for _ in windows)
        total = sum(raw)
        return tuple(weight / total for weight in raw)

    def _effective_volatility_window(self) -> int:
        if self.lookback_windows:
            return self.volatility_window
        return min(self.volatility_window, self.lookback_days)


@dataclass(frozen=True, slots=True)
class MainBoardBreakoutStrategy:
    strategy_id: str
    symbols: tuple[str, ...]
    lookback_days: int = 20
    top_n: int = 5
    max_weight_per_symbol: float = 0.15
    min_amount_cny: float = 10_000_000.0
    moving_average_days: int = 20
    family: str = "main_board"
    rebalance_frequency: str = "daily"

    def generate_targets(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[TargetPosition]:
        diagnostics = self.diagnose(as_of, history, portfolio)
        return [
            TargetPosition(
                symbol=record.symbol,
                target_weight=record.target_weight,
                reason=_format_breakout_reason(record),
            )
            for record in diagnostics
            if record.selected
        ]

    def rank_candidates(
        self,
        context: StrategyContext,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[ScoredCandidate]:
        diagnostics = self.diagnose(context.as_of, history, portfolio, context)
        return [_diagnostic_to_candidate(record) for record in diagnostics]

    def diagnose(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
        context: StrategyContext | None = None,
    ) -> list[StrategyDiagnosticRecord]:
        del portfolio, context
        preliminary: list[StrategyDiagnosticRecord] = []
        for symbol in self.symbols:
            score, raw_features, rejection_reason = self._score_symbol(symbol, history.get(symbol, []))
            preliminary.append(
                StrategyDiagnosticRecord(
                    as_of=as_of,
                    strategy_id=self.strategy_id,
                    family=self.family,
                    symbol=symbol,
                    eligible=rejection_reason is None,
                    selected=False,
                    score=score,
                    raw_features=raw_features,
                    target_weight=0.0,
                    rejection_reason=rejection_reason,
                )
            )

        selected_symbols = {
            record.symbol
            for record in sorted(
                (record for record in preliminary if record.eligible and record.score is not None),
                key=lambda item: item.score,
                reverse=True,
            )[: self.top_n]
        }
        rank_by_symbol, rank_percentile_by_symbol = _rank_eligible(preliminary)
        return [
            StrategyDiagnosticRecord(
                as_of=record.as_of,
                strategy_id=record.strategy_id,
                family=record.family,
                symbol=record.symbol,
                eligible=record.eligible,
                selected=record.symbol in selected_symbols,
                score=record.score,
                rank=rank_by_symbol.get(record.symbol),
                rank_percentile=rank_percentile_by_symbol.get(record.symbol),
                universe_size=len(preliminary),
                raw_features=record.raw_features,
                target_weight=self.max_weight_per_symbol if record.symbol in selected_symbols else 0.0,
                target_weight_before_regime=self.max_weight_per_symbol if record.symbol in selected_symbols else 0.0,
                target_weight_after_regime=self.max_weight_per_symbol if record.symbol in selected_symbols else 0.0,
                rejection_reason=record.rejection_reason,
            )
            for record in preliminary
        ]

    def max_lookback(self) -> int:
        return max(self.lookback_days, self.moving_average_days)

    def is_rebalance_day(self, as_of: date, history: dict[str, list[Bar]]) -> bool:
        del history
        return _is_configured_rebalance_day(self.rebalance_frequency, as_of)

    def _score_symbol(self, symbol: str, bars: list[Bar]) -> tuple[float | None, dict[str, float], str | None]:
        raw_features: dict[str, float] = {}
        if classify_symbol(symbol).board != Board.MAIN:
            return None, raw_features, "not_main_board"
        required_history = max(self.lookback_days, self.moving_average_days)
        if len(bars) <= required_history:
            return None, raw_features, f"insufficient_history_for_window_{required_history}"

        latest = bars[-1]
        amount = traded_amount(latest)
        raw_features["amount_cny"] = amount
        if amount < self.min_amount_cny:
            return None, raw_features, "amount_below_min_amount_cny"
        if is_limit_up_buy_blocked(latest):
            return None, raw_features, "blocked_limit_up_buy"

        ma_value = moving_average(bars, self.moving_average_days)
        if ma_value is None:
            return None, raw_features, f"insufficient_history_for_ma_{self.moving_average_days}"
        raw_features[f"ma_{self.moving_average_days}"] = ma_value
        if latest.close < ma_value:
            return None, raw_features, "below_moving_average"

        score = breakout_score(bars, self.lookback_days)
        if score is None:
            return None, raw_features, f"insufficient_history_for_breakout_{self.lookback_days}"
        raw_features["breakout_score"] = score
        raw_features["score"] = score
        if score <= 0:
            return score, raw_features, "no_breakout"
        return score, raw_features, None


def _is_configured_rebalance_day(frequency: str, as_of: date) -> bool:
    normalized = frequency.strip().lower()
    if normalized in {"", "daily"}:
        return True
    if normalized == "weekly":
        return as_of.weekday() == 0
    if normalized == "monthly":
        return as_of.day <= 7
    return True


def _rank_eligible(
    records: Sequence[StrategyDiagnosticRecord],
) -> tuple[dict[str, int], dict[str, float]]:
    ranked = sorted(
        (record for record in records if record.eligible and record.score is not None),
        key=lambda item: item.score,
        reverse=True,
    )
    rank_by_symbol: dict[str, int] = {}
    percentile_by_symbol: dict[str, float] = {}
    count = len(ranked)
    for rank, record in enumerate(ranked, start=1):
        rank_by_symbol[record.symbol] = rank
        percentile_by_symbol[record.symbol] = _rank_percentile(rank, count)
    return rank_by_symbol, percentile_by_symbol


def _rank_percentile(rank: int, count: int) -> float:
    if count <= 1:
        return 1.0
    return 1.0 - ((rank - 1) / (count - 1))


def _diagnostic_to_candidate(record: StrategyDiagnosticRecord) -> ScoredCandidate:
    return ScoredCandidate(
        strategy_id=record.strategy_id,
        family=record.family,
        symbol=record.symbol,
        score=record.score,
        eligible=record.eligible,
        selected=record.selected,
        rank=record.rank,
        rank_percentile=record.rank_percentile,
        peer_distance=record.peer_distance,
        raw_features=record.raw_features,
        universe_size=record.universe_size,
        normalized_features=record.normalized_features,
        target_weight=record.target_weight,
        rejection_reason=record.rejection_reason,
    )


def _format_etf_reason(record: StrategyDiagnosticRecord) -> str:
    score = record.score if record.score is not None else 0.0
    weighted = record.raw_features.get("weighted_momentum", 0.0)
    volatility_key = next(
        (key for key in sorted(record.raw_features) if key.startswith("annualized_volatility_")),
        "annualized_volatility",
    )
    volatility = record.raw_features.get(volatility_key, 0.0)
    return f"score={score:.4f}; weighted_momentum={weighted:.4f}; vol={volatility:.4f}"


def _format_breakout_reason(record: StrategyDiagnosticRecord) -> str:
    score = record.score if record.score is not None else 0.0
    amount = record.raw_features.get("amount_cny", 0.0)
    return f"breakout={score:.4f}; amount_cny={amount:.0f}"
