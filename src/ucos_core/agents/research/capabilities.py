"""Truthful capability declarations for the Agent 01 production boundary.

This catalog describes repository-backed implementations, not aspirational roadmap
items. Credential status means only that a non-empty setting is present; it does
not validate the credential or prove external service availability.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    status: Literal["implemented", "not_integrated"]
    capabilities: list[str] = Field(default_factory=list, max_length=20)
    credential_status: Literal["present", "missing", "not_required", "not_applicable"]
    limitations: list[str] = Field(default_factory=list, max_length=20)


class AgentCapabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    agent_id: Literal["01"] = "01"
    deployment_model: Literal["single_owner"] = "single_owner"
    providers: list[ProviderCapability]


def build_capability_catalog() -> AgentCapabilityResponse:
    """Return code-grounded integrations and explicitly unimplemented providers."""
    tavily_key = bool(os.getenv("TAVILY_API_KEY", "").strip())
    analyzer_key = bool(os.getenv("ANALYSIS_API_KEY", "").strip())
    analyzer_model = bool(os.getenv("ANALYSIS_MODEL", "gpt-4.1-mini").strip())
    analyzer_url = bool(os.getenv("ANALYSIS_BASE_URL", "https://api.openai.com/v1").strip())

    providers = [
        ProviderCapability(
            provider="tavily_general_web_search",
            status="implemented",
            capabilities=["general_web_search", "source_title_url_excerpt", "retrieval_timestamp"],
            credential_status="present" if tavily_key else "missing",
            limitations=[
                "Credential presence is not validation of the key or live API availability.",
                "Not a platform-owned analytics adapter; private platform metrics are unavailable through this integration.",
                "Publication date, update date, platform metrics, and regional coverage may be absent from retrieved results.",
            ],
        ),
        ProviderCapability(
            provider="openai_compatible_analysis",
            status="implemented",
            capabilities=["evidence_grounded_text_analysis", "numbered_source_citations"],
            credential_status="present" if analyzer_key and analyzer_model and analyzer_url else "missing",
            limitations=[
                "Credential presence is not validation of the key, model, endpoint, or live provider availability.",
                "Analysis is not a sales, conversion, commission, or revenue guarantee.",
                "The analyzer consumes retrieved evidence; it does not create platform-specific API access.",
            ],
        ),
    ]
    for provider, label in [
        ("pinterest", "Pinterest"),
        ("youtube", "YouTube"),
        ("facebook", "Facebook"),
        ("tiktok", "TikTok"),
        ("instagram", "Instagram"),
    ]:
        providers.append(
            ProviderCapability(
                provider=provider,
                status="not_integrated",
                capabilities=[],
                credential_status="not_applicable",
                limitations=[
                    f"No dedicated {label} API adapter is wired into the current runtime.",
                    "Do not claim private analytics, trending metrics, or account-level access.",
                    "Use only authorized public sources until a real provider adapter is implemented and tested.",
                ],
            )
        )
    providers.append(
        ProviderCapability(
            provider="product_affiliate_programs",
            status="not_integrated",
            capabilities=[],
            credential_status="not_applicable",
            limitations=[
                "No verified affiliate-program or product-commerce adapter is wired into the current runtime.",
                "Commission rates, eligibility, attribution rules, stock, price, and sales volume must not be inferred.",
                "Each commercial claim requires a current, traceable source and retrieval date.",
            ],
        )
    )
    return AgentCapabilityResponse(providers=providers)
