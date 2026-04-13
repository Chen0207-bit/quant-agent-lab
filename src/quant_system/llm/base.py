"""Provider-agnostic LLM request and response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system_prompt: str
    user_prompt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LLMResponse:
    status: str
    content: str
    provider: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    def generate(self, request: LLMRequest) -> LLMResponse:
        ...
