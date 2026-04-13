"""Meta agent for deterministic single-day orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_system.agents.monitor_agent import MonitorAgent
from quant_system.agents.position_agent import PositionAgent
from quant_system.agents.regime_agent import RegimeAgent, RegimeState
from quant_system.agents.risk_agent import RiskAgent
from quant_system.agents.signal_agent import SignalAgent
from quant_system.common.models import (
    Bar,
    Fill,
    Instrument,
    Order,
    OrderIntent,
    PositionSnapshot,
    PortfolioConstraints,
    ReconcileReport,
    RiskAction,
    RiskDecision,
    RiskRejection,
    Side,
    StrategyDiagnosticRecord,
    TargetPosition,
    UniverseSnapshot,
)


@dataclass(frozen=True, slots=True)
class MetaAgentDecision:
    mode: str
    reason: str
    can_open_new_positions: bool
    regime_override: RegimeState | None = None


@dataclass(frozen=True, slots=True)
class AgentLoopResult:
    as_of: date
    regime: RegimeState
    targets: tuple[TargetPosition, ...]
    risk_decision: RiskDecision
    orders: tuple[Order, ...]
    fills: tuple[Fill, ...]
    reconcile: ReconcileReport
    summary: str
    meta_decision: MetaAgentDecision | None = None
    strategy_diagnostics: tuple[StrategyDiagnosticRecord, ...] = tuple()


class MetaAgent:
    """Coordinate deterministic agents without taking trading authority.

    MetaAgent can choose safe degradation modes, but it cannot create orders
    directly, approve risk, or bypass the RiskAgent veto.
    """

    def __init__(
        self,
        *,
        regime_agent: RegimeAgent,
        signal_agent: SignalAgent,
        position_agent: PositionAgent,
        risk_agent: RiskAgent,
        monitor_agent: MonitorAgent,
    ) -> None:
        self.regime_agent = regime_agent
        self.signal_agent = signal_agent
        self.position_agent = position_agent
        self.risk_agent = risk_agent
        self.monitor_agent = monitor_agent

    def run_day(
        self,
        *,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
        bars: dict[str, Bar],
        instruments: dict[str, Instrument],
        submitted_orders: list[Order],
        fills: list[Fill],
        reconcile: ReconcileReport,
        universe_snapshot: UniverseSnapshot | None = None,
        portfolio_constraints: PortfolioConstraints | None = None,
    ) -> AgentLoopResult:
        raw_regime = self.regime_agent.detect(history)
        meta_decision = self.decide_regime(raw_regime)
        effective_regime = meta_decision.regime_override or raw_regime

        signal_plan = self.signal_agent.generate_signal_plan(
            as_of=as_of,
            history=history,
            portfolio=portfolio,
            regime=effective_regime,
            universe_snapshot=universe_snapshot,
            portfolio_constraints=portfolio_constraints,
        )
        strategy_diagnostics = list(signal_plan.diagnostics)
        targets = self._apply_meta_boundary(meta_decision, list(signal_plan.targets), portfolio)
        intents = self.position_agent.build_order_intents(
            as_of=as_of,
            targets=targets,
            portfolio=portfolio,
            bars=bars,
            instruments=instruments,
        )
        if not meta_decision.can_open_new_positions:
            intents = [intent for intent in intents if intent.side == Side.SELL]

        risk_decision = self._review_orders(
            as_of=as_of,
            intents=intents,
            portfolio=portfolio,
            bars=bars,
            instruments=instruments,
        )
        summary = self.monitor_agent.render_daily_summary(
            as_of=as_of,
            regime=effective_regime,
            targets=targets,
            risk_decision=risk_decision,
            orders=submitted_orders,
            fills=fills,
            reconcile=reconcile,
            strategy_diagnostics=strategy_diagnostics,
        )
        return AgentLoopResult(
            as_of=as_of,
            regime=effective_regime,
            targets=tuple(targets),
            risk_decision=risk_decision,
            orders=tuple(submitted_orders),
            fills=tuple(fills),
            reconcile=reconcile,
            summary=summary,
            meta_decision=meta_decision,
            strategy_diagnostics=tuple(strategy_diagnostics),
        )

    def decide_regime(self, regime: RegimeState) -> MetaAgentDecision:
        if regime.regime == "crisis":
            return MetaAgentDecision(
                mode="crisis_liquidate",
                reason="crisis regime blocks new openings and allows exits only",
                can_open_new_positions=False,
                regime_override=RegimeState(
                    "crisis",
                    regime.confidence,
                    {"etf_momentum": 0.0, "main_board_breakout": 0.0, "defensive": 1.0, "default": 0.0},
                    regime.reason,
                ),
            )
        if regime.regime == "uncertain":
            return MetaAgentDecision(
                mode="defensive_hold",
                reason="uncertain regime blocks new openings and keeps existing exposure stable",
                can_open_new_positions=False,
                regime_override=RegimeState(
                    "uncertain",
                    regime.confidence,
                    {"etf_momentum": 0.0, "main_board_breakout": 0.0, "defensive": 1.0, "default": 0.0},
                    regime.reason,
                ),
            )
        return MetaAgentDecision(
            mode="normal",
            reason=f"{regime.regime} regime allows normal paper decisions",
            can_open_new_positions=True,
            regime_override=None,
        )

    def _apply_meta_boundary(
        self,
        meta_decision: MetaAgentDecision,
        targets: list[TargetPosition],
        portfolio: PositionSnapshot,
    ) -> list[TargetPosition]:
        if meta_decision.mode == "crisis_liquidate":
            return []
        if meta_decision.mode != "defensive_hold":
            return targets

        equity = max(portfolio.equity, 0.01)
        held_targets: list[TargetPosition] = []
        for symbol, position in sorted(portfolio.positions.items()):
            if position.qty <= 0:
                continue
            held_targets.append(
                TargetPosition(
                    symbol=symbol,
                    target_weight=max(position.market_value / equity, 0.0),
                    reason="meta_defensive_hold_existing_position",
                )
            )
        return held_targets

    def _review_orders(
        self,
        *,
        as_of: date,
        intents: list[OrderIntent],
        portfolio: PositionSnapshot,
        bars: dict[str, Bar],
        instruments: dict[str, Instrument],
    ) -> RiskDecision:
        try:
            return self.risk_agent.review_orders(
                as_of=as_of,
                orders=intents,
                portfolio=portfolio,
                bars=bars,
                instruments=instruments,
            )
        except Exception as exc:
            reason = f"risk_agent_error: {type(exc).__name__}: {exc}"
            rejections = tuple(RiskRejection(intent.order_id, intent.symbol, reason) for intent in intents)
            return RiskDecision(RiskAction.LIQUIDATE_ONLY, tuple(), rejections, (reason,))
