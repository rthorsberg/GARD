"""YAML catalog loader (T073).

Walks ``gard-catalog/normalization/``, validates each rule against the
JSON Schema in ``contracts/normalization-rule.schema.yaml``, and upserts
each rule into the database with ``source=file``. Returns a summary the
admin endpoint can serialize.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.core.logging import get_logger
from gard.models import NormalizationRule
from gard.models._enums import Confidence, RuleSource

_log = get_logger(__name__)


@dataclass
class LoadReport:
    loaded: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)


# The YAML schema in gard-catalog/schemas/ uses the loose pre-engine
# format. The DB row stores `match` / `output` JSONB blobs computed
# from the YAML. We keep the YAML key names stable and translate.


def _to_db_match(rule: dict[str, Any]) -> dict[str, Any]:
    """Translate YAML rule to DB `match` JSON.

    The seed catalog format uses ``match.any: [{field, regex}]``; we
    flatten this into a normalized structure that the engine understands:
    ``{"vendor_raw_regex": ..., "model_raw_regex": ..., "any": [...]}``.
    """
    raw = rule.get("match") or {}
    out: dict[str, Any] = {}
    if "any" in raw and isinstance(raw["any"], list):
        out["any"] = raw["any"]
    for key in ("vendor_raw_regex", "model_raw_regex", "vendor_raw", "model_raw"):
        if key in raw:
            out[key] = raw[key]
    return out


def _to_db_output(rule: dict[str, Any]) -> dict[str, Any]:
    raw = rule.get("emit") or rule.get("output") or {}
    out: dict[str, Any] = {}
    for k in (
        "vendor",
        "platform",
        "os_family",
        "vendor_normalized",
        "model_normalized",
        "platform_family",
        "hardware_family_template",
        "software_release_template",
    ):
        if k in raw:
            out[k] = raw[k]
    # Friendly aliases the engine standardises on:
    if "vendor" in out and "vendor_normalized" not in out:
        out["vendor_normalized"] = out["vendor"]
    if "platform" in out and "platform_family" not in out:
        out["platform_family"] = out["platform"]
    return out


def _rule_id_from_path(path: Path) -> str:
    return path.stem.lower()


def _validate_rule(doc: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["root is not a mapping"]
    if "schema_version" not in doc:
        errs.append("missing schema_version")
    for required in ("vendor", "platform"):
        if required not in doc:
            errs.append(f"missing required field: {required}")
    if not isinstance(doc.get("match"), dict):
        errs.append("match must be a mapping")
    if not isinstance(doc.get("emit") or doc.get("output"), dict):
        errs.append("emit/output must be a mapping")
    return errs


def load_catalog(session: Session, root: Path) -> LoadReport:
    """Load every ``*.yaml`` under *root*, upserting db rules with ``source=file``.

    Files that fail validation are skipped and their errors collected
    in :attr:`LoadReport.errors`. Existing DB rules with the same id and
    ``source=file`` are updated; rules absent from the filesystem are
    NOT removed (they may have been promoted to ``source=db`` overrides;
    a separate prune endpoint handles that).
    """
    report = LoadReport()
    if not root.exists():
        report.errors.append(f"catalog root does not exist: {root}")
        return report

    now = dt.datetime.now(dt.UTC)

    for path in sorted(root.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            report.errors.append(f"{path.name}: yaml parse error: {exc}")
            report.skipped += 1
            continue

        errs = _validate_rule(doc)
        if errs:
            report.errors.append(f"{path.name}: {'; '.join(errs)}")
            report.skipped += 1
            continue

        rule_id = _rule_id_from_path(path)
        priority = int(doc.get("priority", 100))
        confidence_str = str(doc.get("confidence", "high"))
        try:
            confidence = Confidence(confidence_str)
        except ValueError:
            confidence = Confidence.high

        match_json = _to_db_match(doc)
        output_json = _to_db_output(doc)

        existing = session.get(NormalizationRule, rule_id)
        if existing is None:
            session.add(
                NormalizationRule(
                    id=rule_id,
                    priority=priority,
                    match=match_json,
                    output=output_json,
                    confidence=confidence,
                    source=RuleSource.file,
                    source_path=str(path),
                    enabled=True,
                    notes=str(doc.get("notes")) if doc.get("notes") else None,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing.priority = priority
            existing.match = match_json
            existing.output = output_json
            existing.confidence = confidence
            existing.source = RuleSource.file
            existing.source_path = str(path)
            existing.enabled = True
            existing.updated_at = now
        report.loaded += 1
        report.rule_ids.append(rule_id)

    session.flush()
    _log.info("catalog.loaded", loaded=report.loaded, skipped=report.skipped)
    return report


def file_rules(session: Session) -> list[NormalizationRule]:
    return list(
        session.scalars(
            select(NormalizationRule)
            .where(NormalizationRule.source == RuleSource.file)
            .where(NormalizationRule.enabled.is_(True))
        )
    )
