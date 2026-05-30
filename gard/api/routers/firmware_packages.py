"""F2 firmware-package read + blob endpoints (T057).

Surface:

- `GET  /api/v1/firmware/packages`                      list, filtered
- `GET  /api/v1/firmware/packages/{id}`                  one
- `POST /api/v1/firmware/packages/{id}/blob`             upload bytes
- `GET  /api/v1/firmware/packages/{id}/blob`             stream bytes

Reads require `READ_FIRMWARE_CATALOG`. The blob upload requires the
stricter `MANAGE_FIRMWARE_BLOB` permission (lifecycle_manager +
system_admin). Downloads share the read permission — operators that
can see the metadata can pull the bytes.

Upload semantics (FR-029 / FR-031 / FR-033):

- 200 + receipt on successful verified write.
- 422 BLOB_CHECKSUM_MISMATCH when the computed SHA differs from the
  package row's declared value (the temp file is deleted, no DB
  state change occurs).
- 413 BLOB_TOO_LARGE when the stream exceeds
  ``GARD_FIRMWARE_BLOB_MAX_BYTES``.
- 409 BLOB_UPLOAD_IN_PROGRESS when a concurrent writer holds the
  flock; the client should retry after backoff.

Download semantics (FR-032):

- 200 streaming response with ``X-GARD-SHA256`` and
  ``Content-Length`` headers; final on-the-fly SHA verification
  happens at EOF. If it disagrees with the declared SHA the response
  body terminates short and the controller emits a
  ``firmware_catalog.package.blob_read_failed`` audit row.
- 404 PACKAGE_NOT_FOUND when the package id doesn't exist.
- 409 BLOB_NOT_PRESENT when the package has no uploaded bytes yet.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.firmware_package import (
    BlobUploadReceipt,
    FirmwarePackageList,
    FirmwarePackageResponse,
)
from gard.core.audit import emit as audit_emit
from gard.core.blob_store import (
    BlobChecksumMismatch,
    BlobChecksumMismatchOnRead,
    BlobNotPresent,
    BlobTooLarge,
    BlobUploadInProgress,
    key_for_sha256,
)
from gard.core.blob_store.local_fs import LocalFsBlobStore
from gard.core.evidence import emit as evidence_emit
from gard.core.logging import get_correlation_id, get_logger
from gard.core.rbac import Permission, Principal
from gard.core.settings import get_settings
from gard.db.session import get_append_only_session, get_session
from gard.models import FirmwarePackage
from gard.models._enums import ActorType, AuditResult, EvidenceType

_log = get_logger(__name__)

router = APIRouter(prefix="/api/v1/firmware/packages", tags=["firmware-catalog"])


# ---- helpers ---------------------------------------------------------


def _to_response(p: FirmwarePackage) -> FirmwarePackageResponse:
    return FirmwarePackageResponse(
        id=p.id,
        vendor=p.vendor,  # type: ignore[arg-type]
        platform_family=p.platform_family,
        version=p.version,
        sha256=p.sha256,
        byte_size=p.byte_size,
        signed_by=p.signed_by,
        release_date=p.release_date,
        download_url=p.download_url,
        notes=p.notes,
        blob_present=p.blob_present,
        blob_stored_at=p.blob_stored_at,
        loaded_at=p.loaded_at,
        loaded_from_git_sha=p.loaded_from_git_sha,
        source_file_relpath=p.source_file_relpath,
    )


def _get_live_package(session: Session, package_id: uuid.UUID) -> FirmwarePackage:
    p = session.scalar(
        select(FirmwarePackage)
        .where(FirmwarePackage.id == package_id)
        .where(FirmwarePackage.removed_at.is_(None))
    )
    if p is None:
        raise HTTPException(status_code=404, detail="firmware package not found")
    return p


def _blob_store() -> LocalFsBlobStore:
    s = get_settings()
    return LocalFsBlobStore(root=s.blob_root)


# ---- read endpoints --------------------------------------------------


@router.get(
    "",
    response_model=FirmwarePackageList,
    summary="List live firmware packages",
)
def list_(
    _: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    vendor: str | None = Query(default=None),
    platform_family: str | None = Query(default=None),
    blob_present: bool | None = Query(
        default=None,
        description="Filter by upload status (True=blob landed, False=metadata-only).",
    ),
    limit: int = Query(default=100, ge=1, le=500),
) -> FirmwarePackageList:
    stmt = (
        select(FirmwarePackage)
        .where(FirmwarePackage.removed_at.is_(None))
        .order_by(
            FirmwarePackage.vendor,
            FirmwarePackage.platform_family,
            FirmwarePackage.version,
        )
        .limit(limit)
    )
    if vendor is not None:
        stmt = stmt.where(FirmwarePackage.vendor == vendor)
    if platform_family is not None:
        stmt = stmt.where(FirmwarePackage.platform_family == platform_family)
    if blob_present is not None:
        stmt = stmt.where(FirmwarePackage.blob_present == blob_present)

    rows = list(session.scalars(stmt))
    items = [_to_response(r) for r in rows]
    return FirmwarePackageList(items=items, total_returned=len(items))


@router.get(
    "/{package_id}",
    response_model=FirmwarePackageResponse,
    summary="Fetch one firmware package by id",
)
def get_(
    package_id: uuid.UUID,
    _: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
) -> FirmwarePackageResponse:
    return _to_response(_get_live_package(session, package_id))


# ---- blob endpoints --------------------------------------------------


@router.post(
    "/{package_id}/blob",
    response_model=BlobUploadReceipt,
    summary="Upload firmware blob bytes (verified against the package's declared SHA-256)",
)
def upload_blob(
    package_id: uuid.UUID,
    file: UploadFile,
    principal: Principal = Depends(require(Permission.MANAGE_FIRMWARE_BLOB)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> BlobUploadReceipt:
    pkg = _get_live_package(session, package_id)
    settings = get_settings()

    store = _blob_store()
    key = key_for_sha256(pkg.sha256)
    correlation_id = get_correlation_id()
    actor = principal.subject

    try:
        receipt = store.put(
            key,
            file.file,
            expected_sha256=pkg.sha256,
            max_bytes=settings.firmware_blob_max_bytes,
        )
    except BlobChecksumMismatch as exc:
        _log.warning(
            "firmware_blob.upload_mismatch",
            package_id=str(pkg.id),
            expected=pkg.sha256,
            error=str(exc),
        )
        audit_emit(
            session=audit_session,
            action="firmware_catalog.package.blob_upload_rejected",
            object_type="FirmwarePackage",
            object_id=str(pkg.id),
            result=AuditResult.failure,
            actor=actor,
            actor_type=ActorType.user,
            after={
                "reason": "sha256_mismatch",
                "expected_sha256": pkg.sha256,
                "detail": str(exc),
            },
            correlation_id=correlation_id,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "code": "BLOB_CHECKSUM_MISMATCH",
                "message": str(exc),
            },
        ) from exc
    except BlobTooLarge as exc:
        audit_emit(
            session=audit_session,
            action="firmware_catalog.package.blob_upload_rejected",
            object_type="FirmwarePackage",
            object_id=str(pkg.id),
            result=AuditResult.failure,
            actor=actor,
            actor_type=ActorType.user,
            after={
                "reason": "too_large",
                "max_bytes": settings.firmware_blob_max_bytes,
                "detail": str(exc),
            },
            correlation_id=correlation_id,
        )
        raise HTTPException(
            status_code=413,
            detail={
                "code": "BLOB_TOO_LARGE",
                "message": str(exc),
                "max_bytes": settings.firmware_blob_max_bytes,
            },
        ) from exc
    except BlobUploadInProgress as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "BLOB_UPLOAD_IN_PROGRESS",
                "message": str(exc),
            },
        ) from exc

    # Verified write — flip the metadata, emit audit + evidence.
    pkg.blob_present = True
    pkg.blob_stored_at = receipt.stored_at
    session.flush()

    after_payload = {
        "package_id": str(pkg.id),
        "vendor": pkg.vendor,
        "platform_family": pkg.platform_family,
        "version": pkg.version,
        "computed_sha256": receipt.computed_sha256,
        "bytes_written": receipt.bytes_written,
        "stored_at": receipt.stored_at.isoformat(),
        "blob_key": key,
    }
    audit_emit(
        session=audit_session,
        action="firmware_catalog.package.blob_stored",
        object_type="FirmwarePackage",
        object_id=str(pkg.id),
        result=AuditResult.success,
        actor=actor,
        actor_type=ActorType.user,
        after=after_payload,
        correlation_id=correlation_id,
    )
    evidence_emit(
        session=audit_session,
        evidence_type=EvidenceType.firmware_package_upload,
        subject_type="FirmwarePackage",
        subject_id=str(pkg.id),
        actor=actor,
        after_state=after_payload,
        source_checksum=receipt.computed_sha256,
        references={"blob_key": key, "byte_size": pkg.byte_size},
    )

    return BlobUploadReceipt(
        package_id=pkg.id,
        computed_sha256=receipt.computed_sha256,
        bytes_written=receipt.bytes_written,
        stored_at=receipt.stored_at,
        correlation_id=correlation_id,
    )


@router.get(
    "/{package_id}/blob",
    summary="Stream firmware blob bytes with on-the-fly SHA-256 verification",
    response_class=StreamingResponse,
)
def download_blob(
    package_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> StreamingResponse:
    pkg = _get_live_package(session, package_id)

    if not pkg.blob_present:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "BLOB_NOT_PRESENT",
                "message": (
                    f"package {pkg.id} has no uploaded blob; POST .../blob first to provision bytes"
                ),
            },
        )

    store = _blob_store()
    key = key_for_sha256(pkg.sha256)

    try:
        stream = store.get(key, expected_sha256=pkg.sha256, size=pkg.byte_size)
    except BlobNotPresent as exc:
        # Metadata says the blob exists but the FS disagrees — log + 409.
        audit_emit(
            session=audit_session,
            action="firmware_catalog.package.blob_read_failed",
            object_type="FirmwarePackage",
            object_id=str(pkg.id),
            result=AuditResult.failure,
            actor=principal.subject,
            actor_type=ActorType.user,
            after={"reason": "missing_on_disk", "detail": str(exc), "blob_key": key},
            correlation_id=get_correlation_id(),
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "BLOB_NOT_PRESENT_ON_DISK",
                "message": str(exc),
            },
        ) from exc

    correlation_id = get_correlation_id()
    actor = principal.subject

    def _stream() -> Iterator[bytes]:
        try:
            yield from stream.iter_chunks()
            stream.verify_at_eof()
        except BlobChecksumMismatchOnRead as exc:
            # Audit the tamper detection. The stream is already truncated
            # client-side; we can't safely send more bytes after this.
            audit_emit(
                session=audit_session,
                action="firmware_catalog.package.blob_read_failed",
                object_type="FirmwarePackage",
                object_id=str(pkg.id),
                result=AuditResult.failure,
                actor=actor,
                actor_type=ActorType.user,
                after={
                    "reason": "sha256_mismatch_on_read",
                    "expected_sha256": pkg.sha256,
                    "detail": str(exc),
                    "blob_key": key,
                },
                correlation_id=correlation_id,
            )
            audit_session.commit()
            _log.error(
                "firmware_blob.tamper_detected",
                package_id=str(pkg.id),
                expected=pkg.sha256,
                detail=str(exc),
            )
            # Re-raise so the WSGI/ASGI layer logs an error; FastAPI will
            # have already started the 200 response — there is no clean
            # way to signal failure mid-stream other than closing it.
            raise

    headers = {
        "X-GARD-SHA256": pkg.sha256,
        "Content-Length": str(pkg.byte_size),
        "Content-Disposition": (
            f'attachment; filename="{pkg.vendor}-{pkg.platform_family}-{pkg.version}.bin"'
        ),
    }
    # Best-effort audit row for a successful download initiation. Mid-
    # stream failures still flip to blob_read_failed via _stream().
    audit_emit(
        session=audit_session,
        action="firmware_catalog.package.blob_read",
        object_type="FirmwarePackage",
        object_id=str(pkg.id),
        result=AuditResult.success,
        actor=actor,
        actor_type=ActorType.user,
        after={
            "blob_key": key,
            "byte_size": pkg.byte_size,
            "expected_sha256": pkg.sha256,
            "served_at": dt.datetime.now(dt.UTC).isoformat(),
        },
        correlation_id=correlation_id,
    )

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers=headers,
    )
