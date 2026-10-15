"""Versioned L02 research contracts aligned with the frozen UCOS v1.2 baseline."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class ResearchStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    NO_RESULTS = "NO_RESULTS"
    FAILED = "FAILED"


class ResearchContext(BaseModel):
    """Mandatory account/workflow identity carried through the research boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    workflow_id: Identifier
    workflow_step_id: Identifier
    tenant_id: Identifier
    workspace_id: Identifier
    brand_id: Identifier
    account_id: Identifier
    platform: Identifier
    platform_account_id: Identifier
    request_id: Identifier
    correlation_id: Identifier


class ResearchRequest(ResearchContext):
    query: Annotated[str, Field(min_length=3, max_length=1000)]
    max_results: Annotated[int, Field(ge=1, le=10)] = 5


class ResearchSourceObservation(BaseModel):
    """A provider-returned observation with the evidence needed to trace its origin."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: Identifier
    provider: Identifier
    url: HttpUrl
    title: Annotated[str, Field(min_length=1, max_length=1000)]
    snippet: Annotated[str, Field(max_length=12000)]
    observed_at: datetime
    source_timestamp: datetime | None = None
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None = None


class ResearchResult(ResearchContext):
    """Serializable, versioned L02 output; research evidence is never inferred from absence."""

    schema_version: Annotated[str, Field(pattern=r"^1\.0\.0$")] = "1.0.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: ResearchStatus
    query: Annotated[str, Field(min_length=3, max_length=1000)]
    provenance: list[ResearchSourceObservation] = Field(default_factory=list)
    error_code: Identifier | None = None
    retryable: bool = False

    @classmethod
    def failure(
        cls, request: ResearchRequest, *, error_code: str, retryable: bool
    ) -> "ResearchResult":
        return cls(
            **request.model_dump(exclude={"query", "max_results"}),
            status=ResearchStatus.FAILED,
            query=request.query,
            provenance=[],
            error_code=error_code,
            retryable=retryable,
        )
