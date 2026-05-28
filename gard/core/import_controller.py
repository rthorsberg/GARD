"""Import orchestration (T078).

Reads a CSV stream, resolves identity, runs normalization, upserts
devices, persists observations, emits audit + lifecycle evidence, and
materializes an :class:`ImportSummary`. Designed to run synchronously
for small files (≤ ``GARD_CSV_SYNC_THRESHOLD`` rows) and to be invoked
by the worker for larger files (T079).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from gard.api.schemas.csv_row import CSV_SCHEMA_VERSION, CsvRow
from gard.api.schemas.imports import ImportSummary, ImportTotals
from gard.core import audit, evidence
from gard.core.csv_reader import CsvReaderError, iter_rows
from gard.core.device_controller import upsert_from_row
from gard.core.identity import from_csv
from gard.core.logging import get_correlation_id, get_logger
from gard.core.normalization_engine import normalize
from gard.models import DeviceObservation, ImportJob, utcnow
from gard.models._enums import (
    ActorType,
    AuditResult,
    Confidence,
    EvidenceType,
    ImportStatus,
)

_log = get_logger(__name__)

MAX_ERROR_REPORT_ROWS = 50_000


@dataclass
class _Counters:
    total: int = 0
    accepted: int = 0
    rejected: int = 0
    manual_review: int = 0
    duplicate: int = 0
    created: int = 0
    updated: int = 0


def file_sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def find_existing_job(session: Session, sha: str) -> ImportJob | None:
    from sqlalchemy import select

    return session.scalar(
        select(ImportJob).where(ImportJob.file_sha256 == sha, ImportJob.is_override.is_(False))
    )


def run_sync_import(
    *,
    session: Session,
    audit_session: Session,
    actor: str,
    filename: str,
    data: bytes,
    is_override: bool = False,
) -> ImportSummary:
    """Run a sync import end-to-end and return the summary.

    Caller is responsible for committing both ``session`` and
    ``audit_session``. The function flushes on every step so failures
    surface where they belong.
    """
    sha = file_sha256(data)

    job = ImportJob(
        id=uuid.uuid4(),
        filename=filename,
        file_sha256=sha,
        file_size=len(data),
        status=ImportStatus.processing,
        started_at=utcnow(),
        actor=actor,
        is_override=is_override,
    )
    session.add(job)
    session.flush()

    try:
        outcomes = list(iter_rows(data))
    except CsvReaderError as exc:
        job.status = ImportStatus.failed
        job.completed_at = utcnow()
        job.summary = {"error": str(exc)}
        session.flush()
        audit.emit(
            session=audit_session,
            action="import.csv.rejected",
            object_type="ImportJob",
            object_id=str(job.id),
            actor=actor,
            actor_type=ActorType.user,
            result=AuditResult.failure,
            after={"reason": str(exc)},
        )
        return ImportSummary(
            job_id=job.id,
            status="failed",
            totals=ImportTotals(),
            correlation_id=get_correlation_id(),
            warnings=[str(exc)],
            csv_schema_version=CSV_SCHEMA_VERSION,
        )

    counters = _Counters()
    seen_keys: set[str] = set()
    error_rows: list[dict[str, Any]] = []
    last_observation_id: dict[str, uuid.UUID] = {}

    for outcome in outcomes:
        counters.total += 1
        if not outcome.is_valid or outcome.parsed is None:
            counters.rejected += 1
            error_rows.append(
                {
                    "row_number": outcome.row_number,
                    "errors": [{"code": code, "message": msg} for code, msg in outcome.errors],
                    "raw": outcome.raw,
                }
            )
            continue

        row: CsvRow = outcome.parsed
        ident = from_csv(row)
        is_duplicate_in_file = ident.key in seen_keys
        if is_duplicate_in_file:
            counters.duplicate += 1
            error_rows.append(
                {
                    "row_number": outcome.row_number,
                    "errors": [
                        {
                            "code": "ROW_DUPLICATE_IN_FILE",
                            "message": "later row supersedes earlier in same file",
                        }
                    ],
                    "raw": outcome.raw,
                }
            )
            # The duplicate row IS still recorded as a DeviceObservation (so
            # the audit trail captures it), but it is NOT counted as accepted
            # or manual_review — otherwise the contract invariant
            # `total = accepted + rejected + manual_review + duplicate`
            # would not hold.
        seen_keys.add(ident.key)

        norm = normalize(session=session, row=row)

        upsert = upsert_from_row(
            session=session,
            row=row,
            normalization=norm,
            source_system=f"csv-import:{job.id}",
        )
        if upsert.created:
            counters.created += 1
        else:
            counters.updated += 1

        observation = DeviceObservation(
            id=uuid.uuid4(),
            device_id=upsert.device.id,
            import_job_id=job.id,
            observed_firmware=row.observed_firmware,
            observed_bootloader=row.observed_bootloader,
            observed_hardware_revision=row.hardware_revision,
            observed_at=row.observed_at or utcnow(),
            observed_by=f"csv:{filename}",
            confidence=norm.confidence,
            confidence_source=norm.rule_id,
            raw_payload=outcome.raw,
            created_at=utcnow(),
        )
        session.add(observation)
        last_observation_id[ident.key] = observation.id

        if is_duplicate_in_file:
            # already counted under `duplicate` above
            pass
        elif norm.confidence == Confidence.manual_review_required:
            counters.manual_review += 1
        else:
            counters.accepted += 1

    session.flush()

    job.row_count_total = counters.total
    job.row_count_accepted = counters.accepted
    job.row_count_rejected = counters.rejected
    job.row_count_manual_review = counters.manual_review
    job.row_count_duplicate = counters.duplicate
    job.completed_at = utcnow()
    job.status = ImportStatus.completed
    job.error_report = error_rows[:MAX_ERROR_REPORT_ROWS] or None
    summary = ImportSummary(
        job_id=job.id,
        status="completed",
        totals=ImportTotals(
            rows_total=counters.total,
            rows_accepted=counters.accepted,
            rows_rejected=counters.rejected,
            rows_manual_review=counters.manual_review,
            rows_duplicate=counters.duplicate,
            devices_created=counters.created,
            devices_updated=counters.updated,
        ),
        correlation_id=get_correlation_id(),
        csv_schema_version=CSV_SCHEMA_VERSION,
    )
    job.summary = summary.model_dump(mode="json")
    session.flush()

    audit.emit(
        session=audit_session,
        action="import.csv.accepted" if counters.rejected == 0 else "import.job.completed",
        object_type="ImportJob",
        object_id=str(job.id),
        actor=actor,
        actor_type=ActorType.user,
        result=AuditResult.success,
        after=summary.model_dump(mode="json"),
    )
    evidence.emit(
        session=audit_session,
        evidence_type=EvidenceType.import_event,
        subject_type="ImportJob",
        subject_id=str(job.id),
        actor=actor,
        before_state=None,
        after_state=summary.model_dump(mode="json"),
        source_checksum=sha,
        references={"filename": filename},
        timestamp=job.completed_at or utcnow(),
    )

    _log.info(
        "import.completed",
        job_id=str(job.id),
        rows_total=counters.total,
        rows_accepted=counters.accepted,
        rows_rejected=counters.rejected,
        rows_manual_review=counters.manual_review,
    )
    return summary


def make_summary_from_job(job: ImportJob) -> ImportSummary:
    """Reconstruct the summary when re-reading a completed job from the DB."""
    totals = ImportTotals(
        rows_total=job.row_count_total or 0,
        rows_accepted=job.row_count_accepted or 0,
        rows_rejected=job.row_count_rejected or 0,
        rows_manual_review=job.row_count_manual_review or 0,
        rows_duplicate=job.row_count_duplicate or 0,
    )
    status = "completed" if job.status == ImportStatus.completed else "failed"
    return ImportSummary(
        job_id=job.id,
        status=status,  # type: ignore[arg-type]
        totals=totals,
        correlation_id=None,
        csv_schema_version=CSV_SCHEMA_VERSION,
    )


def now_or(ts: dt.datetime | None) -> dt.datetime:
    return ts or utcnow()
