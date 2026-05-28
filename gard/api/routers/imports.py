"""CSV import REST router (T080)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.imports import (
    ImportJobOut,
    ImportReport,
    ImportRowError,
    ImportSummary,
    ImportTotals,
)
from gard.core.import_controller import (
    find_existing_job,
    make_summary_from_job,
    run_sync_import,
)
from gard.core.rbac import Permission, Principal
from gard.db.session import get_append_only_session, get_session
from gard.models import ImportJob

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])


@router.post(
    "/devices/csv",
    response_model=ImportSummary,
    status_code=status.HTTP_200_OK,
    summary="Upload a device-inventory CSV",
)
async def upload_csv(
    file: UploadFile = File(...),
    override: bool = Query(default=False, description="Force re-import of a duplicate file"),
    principal: Principal = Depends(require(Permission.IMPORT_DEVICES)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ImportSummary:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    from gard.core.import_controller import file_sha256

    sha = file_sha256(data)

    if not override:
        existing = find_existing_job(session, sha)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"duplicate file (sha256={sha}); pass override=true to force re-import",
            )

    try:
        summary = run_sync_import(
            session=session,
            audit_session=audit_session,
            actor=principal.subject,
            filename=file.filename or "upload.csv",
            data=data,
            is_override=override,
        )
    except IntegrityError as exc:
        # Two concurrent uploads of the same file body raced past
        # find_existing_job() and both reached the partial unique index.
        # Rollback our session and convert to a deterministic 409 so the
        # client sees the same failure shape as the pre-check path.
        session.rollback()
        if "uq_import_jobs_file_sha256" in str(exc.orig):
            raise HTTPException(
                status_code=409,
                detail=f"duplicate file (sha256={sha}); pass override=true to force re-import",
            ) from exc
        raise
    audit_session.commit()
    return summary


@router.get("/jobs/{job_id}", response_model=ImportJobOut)
def get_job(
    job_id: uuid.UUID,
    _: Principal = Depends(require(Permission.READ_DEVICE)),
    session: Session = Depends(get_session),
) -> ImportJobOut:
    job = session.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return ImportJobOut(
        id=job.id,
        filename=job.filename,
        file_sha256=job.file_sha256,
        file_size=job.file_size,
        status=job.status.value,
        started_at=job.started_at,
        completed_at=job.completed_at,
        actor=job.actor,
        is_override=job.is_override,
        created_at=job.created_at,
        totals=ImportTotals(
            rows_total=job.row_count_total or 0,
            rows_accepted=job.row_count_accepted or 0,
            rows_rejected=job.row_count_rejected or 0,
            rows_manual_review=job.row_count_manual_review or 0,
            rows_duplicate=job.row_count_duplicate or 0,
        ),
    )


@router.get("/jobs/{job_id}/report", response_model=ImportReport)
def get_job_report(
    job_id: uuid.UUID,
    _: Principal = Depends(require(Permission.READ_DEVICE)),
    session: Session = Depends(get_session),
) -> ImportReport:
    job = session.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    raw_errors = job.error_report or []
    items: list[ImportRowError] = []
    for r in raw_errors:
        for e in r.get("errors", []):
            items.append(
                ImportRowError(
                    row_number=int(r.get("row_number", 0)),
                    code=str(e.get("code", "ROW_VALIDATION")),
                    message=str(e.get("message", "")),
                    raw=r.get("raw"),
                )
            )
    return ImportReport(job_id=job.id, row_errors=items, truncated=False)


@router.get("/jobs/{job_id}/summary", response_model=ImportSummary)
def get_job_summary(
    job_id: uuid.UUID,
    _: Principal = Depends(require(Permission.READ_DEVICE)),
    session: Session = Depends(get_session),
) -> ImportSummary:
    job = session.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return make_summary_from_job(job)
