"""F5 — ADR-0016 §B SoD enforcement at the state-machine layer.

This is the application-layer second defence in the triple-layer SoD
strategy (API → controller → DB). These tests exercise the controller
guard exposed via :func:`wave_decide` / :func:`exception_decide`.
"""

from __future__ import annotations

import pytest

from gard.core.uplift_state_machine import (
    SelfApprovalForbidden,
    exception_decide,
    wave_decide,
)
from gard.models._enums import ExceptionState, WaveState

# ---------------------------------------------------------------------------
# Wave SoD
# ---------------------------------------------------------------------------


def test_wave_self_approval_forbidden() -> None:
    """An approver whose subject equals the drafter's subject is refused."""
    with pytest.raises(SelfApprovalForbidden) as ei:
        wave_decide(
            from_state=WaveState.submitted,
            to_state=WaveState.approved,
            actor_kind="approver",
            actor_subject="alice@org",
            drafter_subject="alice@org",
        )
    assert ei.value.subject == "alice@org"
    assert ei.value.edge == (WaveState.submitted.value, WaveState.approved.value)


def test_wave_second_principal_approval_allowed() -> None:
    """A distinct approver subject is allowed."""
    t = wave_decide(
        from_state=WaveState.submitted,
        to_state=WaveState.approved,
        actor_kind="approver",
        actor_subject="bob@org",
        drafter_subject="alice@org",
    )
    assert t.is_sod_edge is True
    assert t.actor_subject == "bob@org"


def test_wave_self_rejection_is_allowed_not_sod() -> None:
    """Self-rejection is explicit drafter withdrawal and is not SoD-bound."""
    t = wave_decide(
        from_state=WaveState.submitted,
        to_state=WaveState.rejected,
        actor_kind="drafter",
        actor_subject="alice@org",
        drafter_subject="alice@org",
    )
    assert t.is_sod_edge is False
    assert t.actor_kind == "drafter"


def test_wave_self_cancellation_is_allowed_not_sod() -> None:
    """A drafter pulling their own draft is not a SoD-protected edge."""
    t = wave_decide(
        from_state=WaveState.draft,
        to_state=WaveState.cancelled,
        actor_kind="drafter",
        actor_subject="alice@org",
        drafter_subject="alice@org",
    )
    assert t.is_sod_edge is False


def test_wave_invalidate_by_system_not_sod_bound() -> None:
    """System-driven invalidate is not subject to SoD."""
    t = wave_decide(
        from_state=WaveState.submitted,
        to_state=WaveState.invalidated,
        actor_kind="system",
        actor_subject="system",
        drafter_subject="alice@org",
    )
    assert t.is_sod_edge is False


# ---------------------------------------------------------------------------
# Exception SoD
# ---------------------------------------------------------------------------


def test_exception_self_approval_forbidden() -> None:
    with pytest.raises(SelfApprovalForbidden) as ei:
        exception_decide(
            from_state=ExceptionState.pending_review,
            to_state=ExceptionState.approved,
            actor_kind="approver",
            actor_subject="alice@org",
            filer_subject="alice@org",
        )
    assert ei.value.subject == "alice@org"


def test_exception_second_principal_approval_allowed() -> None:
    t = exception_decide(
        from_state=ExceptionState.pending_review,
        to_state=ExceptionState.approved,
        actor_kind="approver",
        actor_subject="bob@org",
        filer_subject="alice@org",
    )
    assert t.is_sod_edge is True
    assert t.actor_subject == "bob@org"


def test_exception_self_withdrawal_is_allowed_not_sod() -> None:
    """Withdrawing your own exception is permitted; not a SoD edge."""
    t = exception_decide(
        from_state=ExceptionState.pending_review,
        to_state=ExceptionState.withdrawn,
        actor_kind="filer",
        actor_subject="alice@org",
        filer_subject="alice@org",
    )
    assert t.is_sod_edge is False


def test_exception_rejection_not_sod_bound() -> None:
    """Rejection itself is not SoD-bound (the data-model still requires
    the approver subject to be set, but an approver can have any subject)."""
    t = exception_decide(
        from_state=ExceptionState.pending_review,
        to_state=ExceptionState.rejected,
        actor_kind="approver",
        actor_subject="alice@org",
        filer_subject="alice@org",
    )
    assert t.is_sod_edge is False


def test_exception_lazy_expiry_by_system_not_sod_bound() -> None:
    t = exception_decide(
        from_state=ExceptionState.approved,
        to_state=ExceptionState.expired,
        actor_kind="system",
        actor_subject="system",
        filer_subject="alice@org",
    )
    assert t.is_sod_edge is False
