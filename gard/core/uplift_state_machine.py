"""F5 uplift state machine — pure functions (ADR-0016 §A + §C).

Two finite state machines:

* :class:`WaveTransition` for ``UpliftWave.state``
* :class:`ExceptionTransition` for ``UpliftException.state``

Both are layered on top of a tiny shared kernel that:

1. validates ``(from_state, to_state)`` against the legal-edge table,
2. enforces actor-role expectations for the edge (drafter / approver /
   system / filer),
3. enforces separation-of-duties (ADR-0016 §B) on approval-class edges,
4. returns a :class:`Transition` decision the controller layer can
   apply as a single ``UPDATE ... WHERE state=:expected`` statement.

These functions are deliberately framework-free (no SQLAlchemy, no
HTTP) so unit tests can exercise every legal + illegal edge as a
truth table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gard.models._enums import ExceptionState, WaveState

ActorKind = Literal["drafter", "approver", "system", "filer", "anyone"]


# ---------------------------------------------------------------------------
# Wave state machine — ADR-0016 §A
# ---------------------------------------------------------------------------

# Each edge: (from, to) -> set of legal actor kinds. The actor kind is the
# CALLER'S relationship to the existing row (the drafter who created it, OR
# a second principal acting as approver, OR the system itself for invalidate).
_WAVE_EDGES: dict[tuple[WaveState, WaveState], frozenset[ActorKind]] = {
    # draft → ...
    (WaveState.draft, WaveState.submitted): frozenset({"drafter"}),
    (WaveState.draft, WaveState.cancelled): frozenset({"drafter"}),
    (WaveState.draft, WaveState.invalidated): frozenset({"system"}),
    # submitted → ...
    (WaveState.submitted, WaveState.approved): frozenset({"approver"}),
    (WaveState.submitted, WaveState.rejected): frozenset({"approver", "drafter"}),
    (WaveState.submitted, WaveState.cancelled): frozenset({"drafter"}),
    (WaveState.submitted, WaveState.invalidated): frozenset({"system"}),
}

# Edges where ADR-0016 §B SoD applies (the approver must not be the drafter).
_WAVE_SOD_EDGES: frozenset[tuple[WaveState, WaveState]] = frozenset(
    {
        (WaveState.submitted, WaveState.approved),
    }
)

# Wave terminal states — once here, no further transitions are allowed.
WAVE_TERMINAL: frozenset[WaveState] = frozenset(
    {
        WaveState.approved,
        WaveState.rejected,
        WaveState.cancelled,
        WaveState.invalidated,
    }
)


# ---------------------------------------------------------------------------
# Exception state machine — ADR-0016 §C
# ---------------------------------------------------------------------------

_EXCEPTION_EDGES: dict[tuple[ExceptionState, ExceptionState], frozenset[ActorKind]] = {
    # pending_review → ...
    (ExceptionState.pending_review, ExceptionState.approved): frozenset({"approver"}),
    (ExceptionState.pending_review, ExceptionState.rejected): frozenset({"approver"}),
    (ExceptionState.pending_review, ExceptionState.withdrawn): frozenset({"filer"}),
    # approved → ...
    (ExceptionState.approved, ExceptionState.expired): frozenset({"system"}),
    (ExceptionState.approved, ExceptionState.withdrawn): frozenset({"filer"}),
}

_EXCEPTION_SOD_EDGES: frozenset[tuple[ExceptionState, ExceptionState]] = frozenset(
    {
        (ExceptionState.pending_review, ExceptionState.approved),
    }
)

EXCEPTION_TERMINAL: frozenset[ExceptionState] = frozenset(
    {
        ExceptionState.approved,  # terminal-ish (only system → expired or filer → withdrawn)
        ExceptionState.rejected,
        ExceptionState.expired,
        ExceptionState.withdrawn,
    }
)
# Note: `approved` is "live but not terminal" — only system (expiry) and the
# original filer (withdraw) can act on it. The check below uses the edge
# table itself rather than this set to decide reachability.


# ---------------------------------------------------------------------------
# Decision objects + errors
# ---------------------------------------------------------------------------


class StateMachineError(Exception):
    """Base error for illegal state-machine moves."""


class TransitionForbidden(StateMachineError):  # noqa: N818
    """The (from, to) pair is not a legal edge.

    Named without an ``Error`` suffix on purpose: it's a sentinel that
    callers compare by class identity, mirroring F4's ``ReadinessInputStale``.
    """

    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(f"transition {from_state!r} → {to_state!r} is not a legal edge")
        self.from_state = from_state
        self.to_state = to_state


class ActorKindForbidden(StateMachineError):  # noqa: N818
    """The actor kind is not allowed to drive this edge."""

    def __init__(self, edge: tuple[str, str], actor_kind: str) -> None:
        super().__init__(f"actor_kind={actor_kind!r} cannot drive edge {edge[0]!r} → {edge[1]!r}")
        self.edge = edge
        self.actor_kind = actor_kind


class SelfApprovalForbidden(StateMachineError):  # noqa: N818
    """SoD violation — the approver is the same subject as the drafter/filer."""

    def __init__(self, edge: tuple[str, str], subject: str) -> None:
        super().__init__(
            f"self-approval forbidden on edge {edge[0]!r} → {edge[1]!r} (subject={subject!r})"
        )
        self.edge = edge
        self.subject = subject


@dataclass(frozen=True)
class Transition:
    """A validated, ready-to-apply state transition.

    The controller layer calls :func:`wave_decide` / :func:`exception_decide`,
    receives a :class:`Transition`, and applies it as one atomic
    ``UPDATE ... WHERE state=:from_state`` — ADR-0016 §D optimistic concurrency.
    """

    from_state: str
    to_state: str
    actor_kind: ActorKind
    actor_subject: str
    is_sod_edge: bool


# ---------------------------------------------------------------------------
# Public API — wave
# ---------------------------------------------------------------------------


def wave_legal_edges() -> frozenset[tuple[WaveState, WaveState]]:
    """Return the set of legal wave-state edges (read-only view of the table)."""
    return frozenset(_WAVE_EDGES.keys())


def wave_is_terminal(state: WaveState) -> bool:
    return state in WAVE_TERMINAL


def wave_decide(
    *,
    from_state: WaveState,
    to_state: WaveState,
    actor_kind: ActorKind,
    actor_subject: str,
    drafter_subject: str,
) -> Transition:
    """Validate a wave state transition.

    Raises one of :class:`TransitionForbidden`, :class:`ActorKindForbidden`,
    :class:`SelfApprovalForbidden`. Returns a :class:`Transition` to apply.
    """
    edge = (from_state, to_state)
    legal_actors = _WAVE_EDGES.get(edge)
    if legal_actors is None:
        raise TransitionForbidden(from_state.value, to_state.value)
    if actor_kind not in legal_actors:
        raise ActorKindForbidden((from_state.value, to_state.value), actor_kind)
    is_sod_edge = edge in _WAVE_SOD_EDGES
    if is_sod_edge and actor_subject == drafter_subject:
        raise SelfApprovalForbidden((from_state.value, to_state.value), actor_subject)
    return Transition(
        from_state=from_state.value,
        to_state=to_state.value,
        actor_kind=actor_kind,
        actor_subject=actor_subject,
        is_sod_edge=is_sod_edge,
    )


# ---------------------------------------------------------------------------
# Public API — exception
# ---------------------------------------------------------------------------


def exception_legal_edges() -> frozenset[tuple[ExceptionState, ExceptionState]]:
    return frozenset(_EXCEPTION_EDGES.keys())


def exception_decide(
    *,
    from_state: ExceptionState,
    to_state: ExceptionState,
    actor_kind: ActorKind,
    actor_subject: str,
    filer_subject: str,
) -> Transition:
    """Validate an exception state transition.

    Raises one of :class:`TransitionForbidden`, :class:`ActorKindForbidden`,
    :class:`SelfApprovalForbidden`. Returns a :class:`Transition` to apply.
    """
    edge = (from_state, to_state)
    legal_actors = _EXCEPTION_EDGES.get(edge)
    if legal_actors is None:
        raise TransitionForbidden(from_state.value, to_state.value)
    if actor_kind not in legal_actors:
        raise ActorKindForbidden((from_state.value, to_state.value), actor_kind)
    is_sod_edge = edge in _EXCEPTION_SOD_EDGES
    if is_sod_edge and actor_subject == filer_subject:
        raise SelfApprovalForbidden((from_state.value, to_state.value), actor_subject)
    return Transition(
        from_state=from_state.value,
        to_state=to_state.value,
        actor_kind=actor_kind,
        actor_subject=actor_subject,
        is_sod_edge=is_sod_edge,
    )


__all__ = [
    "EXCEPTION_TERMINAL",
    "WAVE_TERMINAL",
    "ActorKind",
    "ActorKindForbidden",
    "SelfApprovalForbidden",
    "StateMachineError",
    "Transition",
    "TransitionForbidden",
    "exception_decide",
    "exception_legal_edges",
    "wave_decide",
    "wave_is_terminal",
    "wave_legal_edges",
]
