"""Signal aggregation agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from quant_system.agents.regime_agent import RegimeState
from quant_system.common.models import (
    Bar,
    PortfolioConstraints,
    PositionSnapshot,
    ScoredCandidate,
    StrategyContext,
    StrategyDiagnosticRecord,
    TargetPosition,
    UniverseSnapshot,
)
from quant_system.portfolio.construction import apply_portfolio_constraints
from quant_system.strategies.base import Strategy


@dataclass(frozen=True, slots=True)
class SignalPlan:
    targets: tuple[TargetPosition, ...]
    diagnostics: tuple[StrategyDiagnosticRecord, ...]
    construction_notes: tuple[str, ...] = tuple()


class SignalAgent:
    def __init__(self, strategies: Sequence[Strategy]) -> None:
        self.strategies = tuple(strategies)

    def generate_targets(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
        regime: RegimeState,
        universe_snapshot: UniverseSnapshot | None = None,
        portfolio_constraints: PortfolioConstraints | None = None,
    ) -> list[TargetPosition]:
        compatibility_constraints = portfolio_constraints or PortfolioConstraints(
            max_position_weight=1.0,
            max_industry_weight=1.0,
            turnover_budget=2.0,
            min_cash_buffer_pct=0.0,
        )
        return list(
            self.generate_signal_plan(
                as_of=as_of,
                history=history,
                portfolio=portfolio,
                regime=regime,
                universe_snapshot=universe_snapshot,
                portfolio_constraints=compatibility_constraints,
            ).targets
        )

    def generate_signal_plan(
        self,
        *,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
        regime: RegimeState,
        universe_snapshot: UniverseSnapshot | None = None,
        portfolio_constraints: PortfolioConstraints | None = None,
    ) -> SignalPlan:
        constraints = portfolio_constraints or PortfolioConstraints()
        combined: dict[str, TargetPosition] = {}
        diagnostics: list[StrategyDiagnosticRecord] = []

        for strategy in self.strategies:
            strategy_id = strategy.strategy_id
            weight = _strategy_regime_weight(strategy, regime)
            if weight <= 0:
                diagnostics.extend(
                    _diagnostics_after_regime(
                        self._strategy_diagnostics(strategy, as_of, history, portfolio),
                        regime_weight=0.0,
                    )
                )
                continue

            context = StrategyContext(
                as_of=as_of,
                universe_snapshot=universe_snapshot,
                regime_name=regime.regime,
                portfolio_constraints=constraints,
                rebalance_frequency=str(getattr(strategy, "rebalance_frequency", "daily")),
                sleeve_budget=weight,
            )
            if not _is_rebalance_day(strategy, as_of, history):
                diagnostics.extend(
                    _diagnostics_after_regime(
                        self._strategy_diagnostics(strategy, as_of, history, portfolio),
                        regime_weight=0.0,
                    )
                )
                continue

            candidates = self._rank_candidates(strategy, context, history, portfolio)
            if candidates:
                diagnostics.extend(_candidates_to_diagnostics(context.as_of, candidates, weight))
                targets = _candidate_targets(candidates)
            else:
                targets = strategy.generate_targets(as_of, history, portfolio)
                diagnostics.extend(
                    _diagnostics_after_regime(
                        self._strategy_diagnostics(strategy, as_of, history, portfolio),
                        regime_weight=weight,
                    )
                )

            for target in targets:
                scaled_weight = target.target_weight * weight
                if scaled_weight <= 0:
                    continue
                existing = combined.get(target.symbol)
                reason = f"{strategy_id}:{target.reason}; regime={regime.regime}; weight={weight:.2f}"
                if existing is None:
                    combined[target.symbol] = TargetPosition(target.symbol, scaled_weight, reason)
                else:
                    combined[target.symbol] = TargetPosition(
                        target.symbol,
                        existing.target_weight + scaled_weight,
                        f"{existing.reason} | {reason}",
                    )

        adjusted_weights, notes = apply_portfolio_constraints(
            {symbol: target.target_weight for symbol, target in combined.items()},
            portfolio,
            universe_snapshot,
            constraints,
        )
        adjusted_targets = tuple(
            TargetPosition(
                symbol=symbol,
                target_weight=weight,
                reason=_append_notes(_target_reason(symbol, combined), notes),
            )
            for symbol, weight in sorted(adjusted_weights.items())
            if weight > 0
        )
        return SignalPlan(adjusted_targets, tuple(diagnostics), tuple(notes))

    def diagnose_strategies(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[StrategyDiagnosticRecord]:
        diagnostics: list[StrategyDiagnosticRecord] = []
        for strategy in self.strategies:
            diagnostics.extend(self._strategy_diagnostics(strategy, as_of, history, portfolio))
        return diagnostics

    def _rank_candidates(
        self,
        strategy: Strategy,
        context: StrategyContext,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[ScoredCandidate]:
        rank_candidates = getattr(strategy, "rank_candidates", None)
        if not callable(rank_candidates):
            return []
        return list(rank_candidates(context, history, portfolio))

    def _strategy_diagnostics(
        self,
        strategy: Strategy,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[StrategyDiagnosticRecord]:
        diagnose = getattr(strategy, "diagnose", None)
        if not callable(diagnose):
            return []
        return list(diagnose(as_of, history, portfolio))


def _strategy_regime_weight(strategy: Strategy, regime: RegimeState) -> float:
    family = str(getattr(strategy, "family", ""))
    return regime.weights.get(
        strategy.strategy_id,
        regime.weights.get(family, regime.weights.get("default", 0.33)),
    )


def _candidate_targets(candidates: list[ScoredCandidate]) -> list[TargetPosition]:
    return [
        TargetPosition(
            symbol=candidate.symbol,
            target_weight=candidate.target_weight,
            reason=_candidate_reason(candidate),
        )
        for candidate in candidates
        if candidate.selected and candidate.eligible and candidate.target_weight > 0
    ]


def _candidate_reason(candidate: ScoredCandidate) -> str:
    score = candidate.score if candidate.score is not None else 0.0
    rank = candidate.rank if candidate.rank is not None else 0
    return f"family={candidate.family}; rank={rank}; score={score:.4f}"


def _candidates_to_diagnostics(
    as_of: date,
    candidates: list[ScoredCandidate],
    regime_weight: float,
) -> list[StrategyDiagnosticRecord]:
    return [
        StrategyDiagnosticRecord(
            as_of=as_of,
            strategy_id=candidate.strategy_id,
            family=candidate.family,
            symbol=candidate.symbol,
            eligible=candidate.eligible,
            selected=candidate.selected,
            score=candidate.score,
            rank=candidate.rank,
            rank_percentile=candidate.rank_percentile,
            universe_size=candidate.universe_size,
            peer_distance=candidate.peer_distance,
            raw_features=candidate.raw_features,
            normalized_features=candidate.normalized_features,
            target_weight=candidate.target_weight,
            target_weight_before_regime=candidate.target_weight,
            target_weight_after_regime=candidate.target_weight * regime_weight,
            rejection_reason=candidate.rejection_reason,
        )
        for candidate in candidates
    ]


def _diagnostics_after_regime(
    records: list[StrategyDiagnosticRecord],
    *,
    regime_weight: float,
) -> list[StrategyDiagnosticRecord]:
    return [
        StrategyDiagnosticRecord(
            as_of=record.as_of,
            strategy_id=record.strategy_id,
            family=record.family,
            symbol=record.symbol,
            eligible=record.eligible,
            selected=record.selected,
            score=record.score,
            rank=record.rank,
            rank_percentile=record.rank_percentile,
            universe_size=record.universe_size,
            peer_distance=record.peer_distance,
            raw_features=record.raw_features,
            normalized_features=record.normalized_features,
            target_weight=record.target_weight,
            target_weight_before_regime=record.target_weight,
            target_weight_after_regime=record.target_weight * regime_weight,
            rejection_reason=record.rejection_reason,
        )
        for record in records
    ]


def _is_rebalance_day(strategy: Strategy, as_of: date, history: dict[str, list[Bar]]) -> bool:
    is_rebalance_day = getattr(strategy, "is_rebalance_day", None)
    if not callable(is_rebalance_day):
        return True
    return bool(is_rebalance_day(as_of, history))


def _target_reason(symbol: str, combined: dict[str, TargetPosition]) -> str:
    target = combined.get(symbol)
    if target is not None:
        return target.reason
    return "portfolio_constraint_retains_existing_position"


def _append_notes(reason: str, notes: list[str]) -> str:
    if not notes:
        return reason
    return f"{reason}; constraints={','.join(notes)}"
