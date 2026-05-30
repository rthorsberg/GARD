"""Scope-selector grammar evaluator (F2, shared by FirmwareTarget + PrerequisiteRule).

A ``ScopeSelector`` is a small dict matching a Device's facts. Grammar is
intentionally narrow: every key is AND'd; no disjunction in v1 (per
research.md R-8). The vocabulary is fixed and any unknown key raises
:class:`UnknownSelectorKey` so the loader can roll back the whole reload.

Supported keys (all optional; at least one MUST be present per the JSON Schema):

- ``vendor_normalized``: exact string match
- ``platform_family``:   exact string match
- ``region_in``:         set membership (device.region IN [...])
- ``site_in``:           set membership
- ``role_in``:           set membership
- ``hardware_revision_in``: set membership
- ``not_in_state``:      device.lifecycle_state NOT IN [...]
- ``tagged_with``:       deferred — see Constitution-VII / FR-024. Evaluator
                          returns False AND signals via ``predicate_deferred``;
                          callers should treat as "unknown" and never coerce
                          to True.

Specificity (used by FR-009 tie-break): the count of non-null leaf entries.
Set-membership keys count once regardless of list length. Ties on specificity
are broken by ``loaded_at DESC`` at the call site (compliance_controller).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Vocabulary kept in sync with contracts/scope-selector.schema.yaml.
KNOWN_KEYS: frozenset[str] = frozenset(
    {
        "vendor_normalized",
        "platform_family",
        "region_in",
        "site_in",
        "role_in",
        "hardware_revision_in",
        "not_in_state",
        "tagged_with",
    }
)

# Keys whose evaluation is deferred to a later feature. v1 only has tagged_with.
DEFERRED_KEYS: frozenset[str] = frozenset({"tagged_with"})

EXACT_KEYS: frozenset[str] = frozenset({"vendor_normalized", "platform_family"})
SET_MEMBERSHIP_KEYS: frozenset[str] = frozenset(
    {"region_in", "site_in", "role_in", "hardware_revision_in"}
)


class UnknownSelectorKey(ValueError):
    """Raised when a selector contains a key outside ``KNOWN_KEYS``.

    The loader catches this, rolls the reload back, and emits
    ``firmware_catalog.reload_failed`` with the offending file path.
    """


class SelectorEvaluation:
    """Result of evaluating one ``ScopeSelector`` against a Device's facts.

    Carries both the boolean verdict and a flag indicating whether any
    leaf was deferred (so callers can render ``predicate_deferred``
    reasons instead of silently treating deferred-leaf misses as `False`).
    """

    __slots__ = ("deferred_keys", "matched")

    def __init__(self, matched: bool, deferred_keys: frozenset[str] = frozenset()) -> None:
        self.matched = matched
        self.deferred_keys = deferred_keys

    def __repr__(self) -> str:  # pragma: no cover
        return f"SelectorEvaluation(matched={self.matched}, deferred={sorted(self.deferred_keys)})"


def validate_keys(selector: Mapping[str, Any]) -> None:
    """Raise :class:`UnknownSelectorKey` if any key is outside the vocabulary."""
    unknown = set(selector.keys()) - KNOWN_KEYS
    if unknown:
        raise UnknownSelectorKey(
            f"unknown scope-selector keys: {sorted(unknown)} (allowed: {sorted(KNOWN_KEYS)})"
        )


def evaluate(selector: Mapping[str, Any], facts: Mapping[str, Any]) -> SelectorEvaluation:
    """Evaluate ``selector`` against ``facts``.

    ``facts`` is expected to carry the same keys as the selector vocabulary
    (typically pulled from the Device row + its latest observation). Missing
    fact keys count as "not matching" for set-membership/exact predicates;
    they never raise.

    Per research.md R-8, all selector leaves are AND'd: the verdict is True
    iff every leaf matches. Deferred leaves (``tagged_with``) count as
    *non-matching* but the deferred_keys set on the result lets callers
    surface a ``predicate_deferred`` reason rather than silently treating
    deferred-leaf misses as definitive `False`.
    """
    validate_keys(selector)

    deferred: set[str] = set()

    for key, value in selector.items():
        if key in DEFERRED_KEYS:
            deferred.add(key)
            # We deliberately do NOT short-circuit here: a deferred leaf
            # means the verdict is uncertain in principle, but for v1
            # behaviour the deferred leaf can't match anything (Device
            # tags don't exist yet), so the overall verdict is False.
            return SelectorEvaluation(matched=False, deferred_keys=frozenset(deferred))

        if key in EXACT_KEYS:
            if facts.get(key) != value:
                return SelectorEvaluation(matched=False, deferred_keys=frozenset(deferred))
            continue

        if key in SET_MEMBERSHIP_KEYS:
            # selector value is a list; the fact is a scalar string and must be in it.
            # Map e.g. region_in -> "region", site_in -> "site".
            fact_key = key[:-3]  # strip "_in"
            fact_value = facts.get(fact_key)
            if fact_value is None or fact_value not in value:
                return SelectorEvaluation(matched=False, deferred_keys=frozenset(deferred))
            continue

        if key == "not_in_state":
            # device.lifecycle_state must NOT be in the listed states.
            state = facts.get("lifecycle_state")
            if state is None or state in value:
                return SelectorEvaluation(matched=False, deferred_keys=frozenset(deferred))
            continue

        # Unreachable — validate_keys() above would have raised.
        raise UnknownSelectorKey(f"unhandled selector key: {key}")  # pragma: no cover

    return SelectorEvaluation(matched=True, deferred_keys=frozenset(deferred))


def specificity(selector: Mapping[str, Any]) -> int:
    """Count of non-null leaf entries used for tie-break (FR-009).

    Each key in the selector counts as 1 — list-valued keys do not multiply
    the count by their length. This is what makes "more constrained selector
    wins" intuitive and deterministic.

    Unknown keys raise so an under-validated selector can't pretend to be
    more specific than it actually is.
    """
    validate_keys(selector)
    return sum(1 for v in selector.values() if v is not None and v != [])
