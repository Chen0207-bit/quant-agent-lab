"""Disabled LLM client used for audit-safe no-op operation."""

from __future__ import annotations

from quant_system.llm.base import LLMRequest, LLMResponse


class DisabledLLMClient:
    def __init__(self, *, provider: str = "disabled", model: str = "disabled") -> None:
        self.provider = provider
        self.model = model

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            status="skipped",
            content=(
                "LLM reporting is disabled. No model call was made. "
                "Use this artifact as a placeholder for future report-review integration."
            ),
            provider=self.provider,
            model=self.model,
            metadata={
                "reason": "disabled_config",
                "input_keys": sorted(str(key) for key in request.metadata),
            },
        )
