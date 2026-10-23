from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mmc.config.schemas import ErrorKind, ModelSpec, ProviderId

Outcome = Literal["ok", "incomplete", "refused", "blocked"]


class OutputSchema(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    name: str
    json_schema: dict[str, Any]
    model: type[BaseModel]


class ProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    spec: ModelSpec
    system: str | None
    user: str
    max_output_tokens: int
    temperature: float | None
    timeout_s: float
    output_schema: OutputSchema | None = None
    request_tag: str


class TextDelta(BaseModel):
    kind: Literal["delta"] = "delta"
    text: str


class ProviderUsage(BaseModel):
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None
    raw: dict[str, int | None]
    billing_estimated: bool = False


class StreamEnd(BaseModel):
    kind: Literal["end"] = "end"
    outcome: Outcome
    finish_reason: str | None
    request_id: str | None
    usage: ProviderUsage | None


StreamEvent = Annotated[TextDelta | StreamEnd, Field(discriminator="kind")]


class ProviderError(Exception):
    def __init__(self, kind: ErrorKind, message: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.request_id = request_id


class Provider:
    id: ProviderId

    def stream(self, req: ProviderRequest) -> AsyncIterator[StreamEvent]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None
