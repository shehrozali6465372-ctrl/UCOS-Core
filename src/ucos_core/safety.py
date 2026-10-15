"""Fail-closed publication safety rules required by frozen UCOS architecture v1.2."""

from dataclasses import dataclass
from enum import StrEnum


class SafetyViolation(ValueError):
    """Raised when a publication request violates a hard safety gate."""


class ExecutionMode(StrEnum):
    DRAFT = "draft"
    STAGING = "staging"
    PRODUCTION = "production"


class ProviderOutcome(StrEnum):
    FAILED_CONFIRMED = "FAILED_CONFIRMED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    SUBMITTED = "SUBMITTED"
    RECONCILING = "RECONCILING"


@dataclass(frozen=True, slots=True)
class PublicationContext:
    environment: ExecutionMode
    requested_mode: ExecutionMode
    account_mode: ExecutionMode
    platform: str
    requested_visibility: str | None = None
    offline_draft: bool = False


def authorize_publication(context: PublicationContext) -> None:
    """Apply hard gates before any provider mutation; no score can override these checks."""
    if context.environment is ExecutionMode.PRODUCTION and context.offline_draft:
        raise SafetyViolation("offline draft cannot cross the production mutation boundary")

    if (
        context.environment is ExecutionMode.PRODUCTION
        and context.requested_mode is ExecutionMode.STAGING
        and context.account_mode is ExecutionMode.PRODUCTION
    ):
        raise SafetyViolation("staging request is not allowed for a production account in production")

    if (
        context.environment is ExecutionMode.PRODUCTION
        and context.requested_mode is ExecutionMode.PRODUCTION
        and context.platform.strip().casefold() == "tiktok"
        and (context.requested_visibility or "").strip().casefold() != "public"
    ):
        raise SafetyViolation("TikTok production publication requires explicitly public visibility")


def classify_provider_outcome(*, accepted: bool | None, transport_timed_out: bool) -> ProviderOutcome:
    """Preserve ambiguous provider outcomes rather than converting them to failure."""
    if transport_timed_out or accepted is None:
        return ProviderOutcome.OUTCOME_UNKNOWN
    if accepted:
        return ProviderOutcome.SUBMITTED
    return ProviderOutcome.FAILED_CONFIRMED


def next_reconciliation_state(outcome: ProviderOutcome) -> ProviderOutcome:
    """Only an ambiguous outcome enters reconciliation; confirmed states stay explicit."""
    if outcome is ProviderOutcome.OUTCOME_UNKNOWN:
        return ProviderOutcome.RECONCILING
    return outcome


def automatic_retry_allowed(outcome: ProviderOutcome) -> bool:
    """Never blindly repeat a mutation whose external result is ambiguous."""
    return outcome is ProviderOutcome.FAILED_CONFIRMED
