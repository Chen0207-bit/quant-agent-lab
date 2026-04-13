"""Deterministic agent wrappers for the modular monolith."""

from quant_system.agents.data_agent import DataAgent, DataAgentError, DataAgentResult
from quant_system.agents.execution_agent import ExecutionAgent
from quant_system.agents.meta_agent import AgentLoopResult, MetaAgent, MetaAgentDecision
from quant_system.agents.monitor_agent import MonitorAgent
from quant_system.agents.position_agent import PositionAgent
from quant_system.agents.regime_agent import RegimeAgent, RegimeConfig, RegimeState
from quant_system.agents.risk_agent import RiskAgent
from quant_system.agents.signal_agent import SignalAgent

__all__ = [
    "AgentLoopResult",
    "DataAgent",
    "DataAgentError",
    "DataAgentResult",
    "ExecutionAgent",
    "MetaAgent",
    "MetaAgentDecision",
    "MonitorAgent",
    "PositionAgent",
    "RegimeAgent",
    "RegimeConfig",
    "RegimeState",
    "RiskAgent",
    "SignalAgent",
]
