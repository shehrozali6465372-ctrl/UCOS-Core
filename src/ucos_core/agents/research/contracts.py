"""Stable request/response contracts for Research Agent 01."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    source: str
    title: str
    url: str
    excerpt: str
    retrieved_at: str


class ResearchResponse(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    request_id: str
    correlation_id: str
    status: Literal["SUCCEEDED", "NO_RESULTS"]
    analysis: str
    evidence: list[EvidenceItem]
    persisted: bool = True
