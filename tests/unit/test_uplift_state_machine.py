"""F5 — wave + exception state-machine truth tables.

Every cell in ADR-0016 §A and §C is asserted as one of:

- legal edge with the documented actor kinds,
- illegal edge (raises ``TransitionForbidden``),
- legal edge but wrong actor kind (raises ``ActorKindForbidden``).

The SoD layer is exercised in ``test_uplift_separation_of_duties.py``.
"""

from __future__ import annotations

import pytest

from gard.core.uplift_state_machine import (
    EXCEPTION_TERMINAL,
    WAVE_TERMINAL,
    ActorKindForbidden,
    TransitionForbidden,
    exception_decide,
    exception_legal_edges,
    wave_decide,
    wave_is_terminal,
    wave_legal_edges,
)
from gard.models._enums import ExceptionState, WaveState

# ---------------------------------------------------------------------------
# Wave — legal edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_state", "to_state", "actor_kind"),
    [
        # draft → ...
        (WaveState.draft, WaveState.submitted, "drafter"),
        (WaveState.draft, WaveState.cancelled, "drafter"),
        (WaveState.draft, WaveState.invalidated, "system"),
        # submitted → ...
        (WaveState.submitted, WaveState.approved, "approver"),
        (WaveState.submitted, WaveState.rejected, "approver"),
        (WaveState.submitted, WaveState.rejected, "drafter"),  # self-rejection
        (WaveState.submitted, WaveState.cancelled, "drafter"),
        (WaveState.submitted, WaveState.invalidated, "system"),
    ],
)
def test_wave_legal_edge_accepted(
    from_state: WaveState, to_state: WaveState, actor_kind: str
) -> None:
    t = wave_decide(
        from_state=from_state,
        to_state=to_state,
        actor_kind=actor_kind,  # type: ignore[arg-type]
        actor_subject="alice" if actor_kind != "drafter" else "drafter@org",
        drafter_subject="drafter@org",
    )
    assert t.from_state == from_state.value
    assert t.to_state == to_state.value


def test_wave_legal_edges_match_adr_0016_table() -> None:
    """Pin the legal-edge set against the ADR-0016 §A matrix."""
    expected = {
        (WaveState.draft, WaveState.submitted),
        (WaveState.draft, WaveState.cancelled),
        (WaveState.draft, WaveState.invalidated),
        (WaveState.submitted, WaveState.approved),
        (WaveState.submitted, WaveState.rejected),
        (WaveState.submitted, WaveState.cancelled),
        (WaveState.submitted, WaveState.invalidated),
    }
    assert wave_legal_edges() == expected


# ---------------------------------------------------------------------------
# Wave — illegal edges (every non-listed cell)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        # from terminal states — nothing leaves
        (WaveState.approved, WaveState.draft),
        (WaveState.approved, WaveState.submitted),
        (WaveState.approved, WaveState.rejected),
        (WaveState.rejected, WaveState.approved),
        (WaveState.cancelled, WaveState.draft),
        (WaveState.invalidated, WaveState.approved),
        # backward edges
        (WaveState.submitted, WaveState.draft),
        # approve from draft (must go through submitted)
        (WaveState.draft, WaveState.approved),
        # reject from draft
        (WaveState.draft, WaveState.rejected),
        # self-edge
        (WaveState.draft, WaveState.draft),
        (WaveState.submitted, WaveState.submitted),
    ],
)
def test_wave_illegal_edge_rejected(from_state: WaveState, to_state: WaveState) -> None:
    with pytest.raises(TransitionForbidden) as ei:
        wave_decide(
            from_state=from_state,
            to_state=to_state,
            actor_kind="drafter",
            actor_subject="alice",
            drafter_subject="alice",
        )
    assert ei.value.from_state == from_state.value
    assert ei.value.to_state == to_state.value


# ---------------------------------------------------------------------------
# Wave — wrong actor kind on a legal edge
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_state", "to_state", "wrong_kind"),
    [
        # only drafter can submit
        (WaveState.draft, WaveState.submitted, "approver"),
        (WaveState.draft, WaveState.submitted, "system"),
        # only drafter can cancel
        (WaveState.draft, WaveState.cancelled, "approver"),
        (WaveState.submitted, WaveState.cancelled, "approver"),
        # only system can invalidate
        (WaveState.draft, WaveState.invalidated, "drafter"),
        (WaveState.submitted, WaveState.invalidated, "drafter"),
        # only approver can approve
        (WaveState.submitted, WaveState.approved, "drafter"),
        (WaveState.submitted, WaveState.approved, "system"),
    ],
)
def test_wave_wrong_actor_kind_rejected(
    from_state: WaveState, to_state: WaveState, wrong_kind: str
) -> None:
    with pytest.raises(ActorKindForbidden):
        wave_decide(
            from_state=from_state,
            to_state=to_state,
            actor_kind=wrong_kind,  # type: ignore[arg-type]
            actor_subject="alice",
            drafter_subject="bob",
        )


# ---------------------------------------------------------------------------
# Wave — terminal classification
# ---------------------------------------------------------------------------


def test_wave_terminal_set_is_authoritative() -> None:
    expected_terminal = {
        WaveState.approved,
        WaveState.rejected,
        WaveState.cancelled,
        WaveState.invalidated,
    }
    assert expected_terminal == WAVE_TERMINAL
    assert not wave_is_terminal(WaveState.draft)
    assert not wave_is_terminal(WaveState.submitted)
    assert wave_is_terminal(WaveState.approved)
    assert wave_is_terminal(WaveState.invalidated)


# ---------------------------------------------------------------------------
# Exception — legal edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_state", "to_state", "actor_kind"),
    [
        (ExceptionState.pending_review, ExceptionState.approved, "approver"),
        (ExceptionState.pending_review, ExceptionState.rejected, "approver"),
        (ExceptionState.pending_review, ExceptionState.withdrawn, "filer"),
        (ExceptionState.approved, ExceptionState.expired, "system"),
        (ExceptionState.approved, ExceptionState.withdrawn, "filer"),
    ],
)
def test_exception_legal_edge_accepted(
    from_state: ExceptionState, to_state: ExceptionState, actor_kind: str
) -> None:
    t = exception_decide(
        from_state=from_state,
        to_state=to_state,
        actor_kind=actor_kind,  # type: ignore[arg-type]
        actor_subject="alice" if actor_kind != "filer" else "filer@org",
        filer_subject="filer@org",
    )
    assert t.from_state == from_state.value
    assert t.to_state == to_state.value


def test_exception_legal_edges_match_adr_0016_table() -> None:
    expected = {
        (ExceptionState.pending_review, ExceptionState.approved),
        (ExceptionState.pending_review, ExceptionState.rejected),
        (ExceptionState.pending_review, ExceptionState.withdrawn),
        (ExceptionState.approved, ExceptionState.expired),
        (ExceptionState.approved, ExceptionState.withdrawn),
    }
    assert exception_legal_edges() == expected


# ---------------------------------------------------------------------------
# Exception — illegal edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        # nothing leaves a real terminal
        (ExceptionState.rejected, ExceptionState.approved),
        (ExceptionState.expired, ExceptionState.approved),
        (ExceptionState.withdrawn, ExceptionState.approved),
        # cannot go back to pending_review from anywhere
        (ExceptionState.approved, ExceptionState.pending_review),
        (ExceptionState.rejected, ExceptionState.pending_review),
        # cannot reject after approve
        (ExceptionState.approved, ExceptionState.rejected),
        # self-loops
        (ExceptionState.pending_review, ExceptionState.pending_review),
        (ExceptionState.approved, ExceptionState.approved),
    ],
)
def test_exception_illegal_edge_rejected(
    from_state: ExceptionState, to_state: ExceptionState
) -> None:
    with pytest.raises(TransitionForbidden):
        exception_decide(
            from_state=from_state,
            to_state=to_state,
            actor_kind="approver",
            actor_subject="alice",
            filer_subject="bob",
        )


# ---------------------------------------------------------------------------
# Exception — wrong actor kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_state", "to_state", "wrong_kind"),
    [
        (ExceptionState.pending_review, ExceptionState.approved, "filer"),
        (ExceptionState.pending_review, ExceptionState.approved, "system"),
        (ExceptionState.pending_review, ExceptionState.rejected, "filer"),
        (ExceptionState.pending_review, ExceptionState.withdrawn, "approver"),
        (ExceptionState.approved, ExceptionState.expired, "filer"),
        (ExceptionState.approved, ExceptionState.expired, "approver"),
        (ExceptionState.approved, ExceptionState.withdrawn, "approver"),
    ],
)
def test_exception_wrong_actor_kind_rejected(
    from_state: ExceptionState, to_state: ExceptionState, wrong_kind: str
) -> None:
    with pytest.raises(ActorKindForbidden):
        exception_decide(
            from_state=from_state,
            to_state=to_state,
            actor_kind=wrong_kind,  # type: ignore[arg-type]
            actor_subject="alice",
            filer_subject="bob",
        )


def test_exception_terminal_set_includes_approved_for_completeness() -> None:
    # `approved` is "live but not terminal-from-routers'-perspective"; the
    # constant nevertheless lists it because only system (expiry) and the
    # original filer (withdraw) can act on it — operator-facing flows treat
    # it as terminal.
    assert ExceptionState.approved in EXCEPTION_TERMINAL
    assert ExceptionState.expired in EXCEPTION_TERMINAL
    assert ExceptionState.withdrawn in EXCEPTION_TERMINAL
    assert ExceptionState.pending_review not in EXCEPTION_TERMINAL
