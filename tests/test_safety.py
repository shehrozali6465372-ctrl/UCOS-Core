import pytest

from ucos_core.safety import (
    ExecutionMode,
    ProviderOutcome,
    PublicationContext,
    SafetyViolation,
    authorize_publication,
    automatic_retry_allowed,
    classify_provider_outcome,
    next_reconciliation_state,
)


def ctx(**overrides):
    values = {
        "environment": ExecutionMode.PRODUCTION,
        "requested_mode": ExecutionMode.PRODUCTION,
        "account_mode": ExecutionMode.PRODUCTION,
        "platform": "youtube",
        "requested_visibility": "public",
        "offline_draft": False,
    }
    values.update(overrides)
    return PublicationContext(**values)


def test_offline_draft_is_blocked_at_production_boundary():
    with pytest.raises(SafetyViolation, match="offline draft"):
        authorize_publication(ctx(offline_draft=True))


def test_staging_request_cannot_target_production_account_in_production():
    with pytest.raises(SafetyViolation, match="staging request"):
        authorize_publication(ctx(requested_mode=ExecutionMode.STAGING))


def test_tiktok_production_requires_explicit_public_visibility():
    with pytest.raises(SafetyViolation, match="public visibility"):
        authorize_publication(ctx(platform="TikTok", requested_visibility="private"))


def test_tiktok_production_with_explicit_public_visibility_passes():
    authorize_publication(ctx(platform="tiktok", requested_visibility="public"))


def test_timeout_remains_unknown_and_enters_reconciliation_without_retry():
    outcome = classify_provider_outcome(accepted=None, transport_timed_out=True)
    assert outcome is ProviderOutcome.OUTCOME_UNKNOWN
    assert next_reconciliation_state(outcome) is ProviderOutcome.RECONCILING
    assert not automatic_retry_allowed(outcome)


def test_accepted_provider_call_is_submitted_not_claimed_public():
    outcome = classify_provider_outcome(accepted=True, transport_timed_out=False)
    assert outcome is ProviderOutcome.SUBMITTED
    assert not automatic_retry_allowed(outcome)


def test_explicit_rejection_is_confirmed_failure():
    outcome = classify_provider_outcome(accepted=False, transport_timed_out=False)
    assert outcome is ProviderOutcome.FAILED_CONFIRMED
    assert automatic_retry_allowed(outcome)
