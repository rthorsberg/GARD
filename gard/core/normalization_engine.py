"""Normalization rule engine (T074).

Tier-aware resolution per ADR-0010:

1. **Manual mapping** — explicit operator override per observation.
2. **DB override rule** — ``source=db``, hot edits.
3. **File rule** — ``source=file``, version-controlled YAML.

Within a tier, ``priority DESC`` then ``specificity DESC`` then a
deterministic tiebreaker decide the winner. The function returns the
match together with the *reason chain* the envelope helper renders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.schemas.csv_row import CsvRow
from gard.core.envelope import Reason
from gard.models import ManualMapping, NormalizationRule
from gard.models._enums import Confidence, RuleSource


@dataclass(frozen=True)
class NormalizationResult:
    matched: bool
    rule_id: str | None
    tier: str  # "manual" | "db" | "file"
    output: dict[str, Any]
    confidence: Confidence
    reasons: list[Reason]
    specificity: int = 0


def specificity(rule_match: dict[str, Any]) -> int:
    """Compute specificity from rule match shape (exact +2, regex +1)."""
    score = 0
    for k, v in rule_match.items():
        if k == "any" and isinstance(v, list):
            score += len(v)  # each predicate adds at least one
            continue
        if k.endswith("_regex"):
            score += 1
        else:
            score += 2 if v is not None and v != "" else 0
    return score


def _normalize_field(name: str, row: CsvRow) -> str:
    # Maps catalog field paths like "raw.os_string" to row attributes.
    # Today we only know vendor_raw / model_raw / observed_firmware /
    # platform_family_raw. The catalog uses "raw.X" — we strip the prefix.
    base = name.removeprefix("raw.")
    aliases = {
        "os_string": "observed_firmware",
        "snmp_sys_descr": "observed_firmware",  # heuristic in v1
        "model_id": "model_raw",
        "vendor": "vendor_raw",
        "os_version": "observed_firmware",
    }
    attr = aliases.get(base, base)
    return str(getattr(row, attr, "") or "")


def _row_matches(rule: dict[str, Any], row: CsvRow) -> tuple[bool, str | None]:
    """Apply a rule's `match` clause to the row.

    Returns ``(matched, detail)``. Detail is a short human description
    of which clause fired, used to render the envelope reason.
    """
    if not rule:
        return False, None

    if "any" in rule:
        for pred in rule["any"]:
            field = pred.get("field", "")
            target = _normalize_field(field, row)
            if not target:
                continue
            if "regex" in pred:
                try:
                    if re.search(pred["regex"], target):
                        return True, f"any[{field} ~ {pred['regex']}]"
                except re.error:
                    continue
            elif "equals" in pred and target.lower() == str(pred["equals"]).lower():
                return True, f"any[{field} == {pred['equals']}]"
        return False, None

    # Field-keyed regex form (vendor_raw_regex, model_raw_regex, ...).
    for key, pattern in rule.items():
        if not key.endswith("_regex"):
            continue
        attr = key.removesuffix("_regex")
        target = str(getattr(row, attr, "") or "")
        if not target:
            return False, None
        try:
            if not re.search(pattern, target):
                return False, None
        except re.error:
            return False, None

    # Exact-equality keys (vendor_raw, model_raw without _regex suffix).
    for key, expected in rule.items():
        if key.endswith("_regex") or key == "any":
            continue
        target = str(getattr(row, key, "") or "")
        if target.lower() != str(expected).lower():
            return False, None

    return True, "field-match"


def _manual_mapping_for_observation(
    session: Session, observation_id: Any | None
) -> ManualMapping | None:
    if observation_id is None:
        return None
    return session.scalar(
        select(ManualMapping)
        .where(ManualMapping.observation_id == observation_id, ManualMapping.enabled.is_(True))
        .limit(1)
    )


def _select_rules(session: Session) -> tuple[list[NormalizationRule], list[NormalizationRule]]:
    """Return (db_rules, file_rules), both sorted highest-priority first."""
    rows = list(
        session.scalars(
            select(NormalizationRule)
            .where(NormalizationRule.enabled.is_(True))
            .order_by(NormalizationRule.priority.desc(), NormalizationRule.created_at.desc())
        )
    )
    db = [r for r in rows if r.source == RuleSource.db]
    file_ = [r for r in rows if r.source == RuleSource.file]
    return db, file_


def normalize(
    *,
    session: Session,
    row: CsvRow,
    observation_id: Any | None = None,
) -> NormalizationResult:
    """Resolve normalization for one row using the three-tier engine."""
    # Tier 1: manual mapping ------------------------------------------------
    mm = _manual_mapping_for_observation(session, observation_id)
    if mm is not None:
        return NormalizationResult(
            matched=True,
            rule_id=f"manual:{mm.id}",
            tier="manual",
            output={
                "vendor_normalized": mm.vendor_normalized,
                "model_normalized": mm.model_normalized,
                "platform_family": mm.platform_family,
            },
            confidence=Confidence.exact,
            reasons=[
                Reason(kind="manual_mapping", ref=str(mm.id), detail=mm.reason),
            ],
            specificity=99,
        )

    db_rules, file_rules_ = _select_rules(session)

    # Tier 2: DB overrides --------------------------------------------------
    for r in sorted(db_rules, key=lambda x: (-x.priority, -specificity(x.match))):
        ok, detail = _row_matches(r.match, row)
        if ok:
            return NormalizationResult(
                matched=True,
                rule_id=r.id,
                tier="db",
                output=dict(r.output),
                confidence=r.confidence,
                reasons=[Reason(kind="rule_match", ref=r.id, detail=f"db rule: {detail}")],
                specificity=specificity(r.match),
            )

    # Tier 3: File rules ----------------------------------------------------
    for r in sorted(file_rules_, key=lambda x: (-x.priority, -specificity(x.match))):
        ok, detail = _row_matches(r.match, row)
        if ok:
            return NormalizationResult(
                matched=True,
                rule_id=r.id,
                tier="file",
                output=dict(r.output),
                confidence=r.confidence,
                reasons=[Reason(kind="rule_match", ref=r.id, detail=f"file rule: {detail}")],
                specificity=specificity(r.match),
            )

    # No match → manual_review_required
    return NormalizationResult(
        matched=False,
        rule_id=None,
        tier="none",
        output={},
        confidence=Confidence.manual_review_required,
        reasons=[
            Reason(
                kind="missing_input",
                ref=None,
                detail=(
                    f"no rule matched vendor_raw={row.vendor_raw!r} model_raw={row.model_raw!r}"
                ),
            )
        ],
    )
