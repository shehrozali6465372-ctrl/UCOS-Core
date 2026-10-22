"""Versioned research request/result contracts for Agent 01.

Evidence metadata is explicit and conservative: unknown source facts remain null,
and retrieval timestamp must not be mistaken for publication/update time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ucos_core.agents.research.evidence_url import is_valid_evidence_url


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    brand_id: str = Field(min_length=1, max_length=128)
    workflow_id: str = Field(min_length=1, max_length=128)
    workflow_step_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=3, max_length=2000)
    max_results: int = Field(default=5, ge=1, le=10)


class EvidenceItem(BaseModel):
    """A retrieved evidence item with provenance; absent metadata is not inferred."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2048)
    excerpt: str = Field(max_length=8000)
    retrieved_at: datetime
    published_at: datetime | None = None
    updated_at: datetime | None = None
    platform: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    metric_name: str | None = Field(default=None, max_length=200)
    metric_value: float | None = None
    metric_unit: str | None = Field(default=None, max_length=100)
    evidence_kind: Literal[
        "direct", "reported", "proxy", "inference", "unknown"
    ] = "unknown"
    reliability: Literal["high", "medium", "low", "unverified"] = "unverified"
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    corroboration: Literal["corroborated", "conflicted", "single_source", "unknown"] = "unknown"
    limitations: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        """Validate evidence URL syntax; this is not a network-level SSRF defense."""
        if not is_valid_evidence_url(value):
            raise ValueError(
                "evidence URL must be valid HTTP(S) without embedded credentials"
            )
        return value

    @field_validator("retrieved_at", "published_at", "updated_at")
    @classmethod
    def require_timezone_for_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("evidence timestamps must include a timezone")
        if value is not None:
            return value.astimezone(UTC)
        return value


class ResearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.1.0"] = "1.1.0"
    request_id: str
    correlation_id: str
    status: Literal["SUCCEEDED", "NO_RESULTS"]
    analysis: str
    evidence: list[EvidenceItem]
    persisted: bool = True


class ResearchTaskResponse(BaseModel):
    """Scope-bound view of a durable research request, including in-progress work."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    request_id: str
    correlation_id: str
    status: Literal["IN_PROGRESS", "SUCCEEDED", "NO_RESULTS"]
    analysis: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    created_at: datetime
    persisted: bool = True
