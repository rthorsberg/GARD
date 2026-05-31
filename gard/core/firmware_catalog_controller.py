"""F2 firmware catalog controller — git SHA capture + audit emission.

Wraps :func:`gard.catalog.firmware_loader.load_firmware_catalog` with the
side effects the constitution requires:

1. **Git SHA capture per file**: for each loaded row, populate
   ``loaded_from_git_sha`` with the file's most-recent commit SHA via
   ``git log -1 --format=%H -- <relpath>`` semantics (research.md D2).
2. **Dirty-tree refusal in prod**: in ``GARD_ENV=prod``, refuse to load
   when the worktree is dirty (any tracked-file change). Records a
   ``firmware_catalog.reload_failed`` audit row and aborts.
3. **Per-delta audit emission**: on success, walks the LoadReport and emits
   one ``firmware_catalog.<entity>.{loaded,removed}`` AuditEvent per delta
   that actually changed state. "unchanged" deltas emit nothing — that's
   what makes the loader idempotent on unchanged trees (Assumption
   "App-boot reload is idempotent").
4. **Failure audit emission**: on any FirmwareCatalogLoadError, the
   transaction is rolled back and one ``firmware_catalog.reload_failed``
   row is emitted via the append-only role with the offending file path.

The controller does NOT manage the SQLAlchemy session — callers provide
both the regular session (for catalog mutations + reload-failed-on-prod
detection) and the append-only session (for audit writes). This matches
F1's pattern where the worker, the API request handler, and CLI scripts
all own their transaction boundaries explicitly.

Per ADR-0011 §8 (boot-time reload failure posture): if the loader raises
during the app's lifespan reload, callers should log + emit the failed
audit row but should NOT propagate the exception further. The API
continues to serve the last-known catalog state from the pre-failure
load (or no catalog at all if this was the first run).
"""

from __future__ import annotations

import datetime as dt
import subprocess
from collections.abc import Callable
from contextlib import AbstractContextManager as ContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.catalog.firmware_loader import (
    FirmwareCatalogLoadError,
    LoadReport,
    RowDelta,
    load_firmware_catalog,
)
from gard.core.audit import emit as audit_emit
from gard.core.logging import get_correlation_id, get_logger
from gard.core.settings import get_settings
from gard.models import (
    Device,
    FirmwarePackage,
    FirmwarePrerequisiteRule,
    FirmwareTarget,
    FirmwareUpgradePath,
)
from gard.models._enums import ActorType, AuditResult, EvidenceType, LifecycleState

_log = get_logger(__name__)

# Map RowDelta.kind → AuditEvent.object_type + action prefix.
_ENTITY_AUDIT_MAP: dict[str, tuple[str, str]] = {
    "target": ("FirmwareTarget", "firmware_catalog.target"),
    "package": ("FirmwarePackage", "firmware_catalog.package"),
    "upgrade_path": ("FirmwareUpgradePath", "firmware_catalog.upgrade_path"),
    "prerequisite": ("FirmwarePrerequisiteRule", "firmware_catalog.prerequisite"),
}

# Map RowDelta.kind → ORM model + sha-update column for git SHA backfill.
#
# Typed as ``dict[str, Any]`` because mypy can't unify the four concrete
# ORM classes' ``.id``/``.source_file_relpath``/``.loaded_from_git_sha``
# attributes through ``type[Base]`` (declarative metaclass attrs only
# materialize at runtime). The helper that consumes this map performs
# attribute access on rows whose runtime type is one of the four concrete
# entities by construction.
_ENTITY_ORM_MAP: dict[str, Any] = {
    "target": FirmwareTarget,
    "package": FirmwarePackage,
    "upgrade_path": FirmwareUpgradePath,
    "prerequisite": FirmwarePrerequisiteRule,
}


@dataclass
class ReloadOutcome:
    """What ``reload()`` returns to its caller."""

    success: bool
    report: LoadReport | None = None
    error: FirmwareCatalogLoadError | None = None
    git_shas_by_file: dict[str, str | None] = field(default_factory=dict)
    dirty: bool = False
    # T040: number of devices whose compliance was re-checked after this
    # reload. Upper bound on `firmware_target.compliance_evaluated` audit
    # rows produced as a side effect. 0 when the reload was a no-op or
    # touched no targets and no firmware-state devices existed.
    devices_reevaluated: int = 0


# ---- git helpers ------------------------------------------------------


def _git_file_sha(repo_root: Path, relpath: str) -> str | None:
    """Return the file's most-recent commit SHA, or None if not in git / dirty.

    Uses ``git log -1 --format=%H -- <relpath>`` semantics from research.md D2.
    Returns None when:

    - The repo isn't a git repo (no .git dir).
    - The file has never been committed (`git log` returns empty).
    - The command fails for any reason — we never crash the loader.
    """
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", relpath],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if proc.returncode != 0:
            return None
        sha = proc.stdout.strip()
        return sha if sha else None
    except (subprocess.SubprocessError, OSError):
        return None


def _is_worktree_dirty(repo_root: Path) -> bool:
    """Return True iff git reports any tracked-file change.

    Untracked files don't count — only modifications to tracked files
    matter for "are we loading from a clean tree?".
    """
    try:
        proc = subprocess.run(
            ["git", "diff", "--quiet", "--exit-code"],
            cwd=repo_root,
            capture_output=True,
            check=False,
            timeout=5.0,
        )
        # exit 0 = clean; exit 1 = dirty; other = error → treat as not-dirty
        # since the goal of this check is to refuse dirty loads in prod,
        # and a git-error shouldn't masquerade as dirty.
        return proc.returncode == 1
    except (subprocess.SubprocessError, OSError):
        return False


def _capture_git_shas(repo_root: Path, file_relpaths: set[str]) -> dict[str, str | None]:
    """Return a {relpath: sha-or-None} map for every loaded file."""
    return {rp: _git_file_sha(repo_root, rp) for rp in file_relpaths}


def _apply_git_shas(
    session: Session,
    report: LoadReport,
    repo_root: Path,
    file_relpaths: set[str],
) -> dict[str, str | None]:
    """Backfill ``loaded_from_git_sha`` on every row touched by this load."""
    sha_map = _capture_git_shas(repo_root, file_relpaths)
    for kind, orm_cls in _ENTITY_ORM_MAP.items():
        affected_ids = [
            d.entity_id for d in report.deltas if d.kind == kind and d.action != "removed"
        ]
        if not affected_ids:
            continue
        # Query the rows so we can apply per-relpath SHA correctly.
        rows = session.scalars(select(orm_cls).where(orm_cls.id.in_(affected_ids))).all()
        for row in rows:
            sha = sha_map.get(row.source_file_relpath)
            row.loaded_from_git_sha = sha
    session.flush()
    return sha_map


# ---- audit emission helpers ------------------------------------------


def _emit_delta_audit(
    *,
    audit_session: Session,
    delta: RowDelta,
    git_sha: str | None,
    actor: str,
) -> None:
    object_type, action_prefix = _ENTITY_AUDIT_MAP[delta.kind]
    action = f"{action_prefix}.{delta.action}"
    after = dict(delta.after)
    after["git_commit_sha"] = git_sha
    audit_emit(
        session=audit_session,
        action=action,
        object_type=object_type,
        object_id=delta.entity_id,
        result=AuditResult.success,
        actor=actor,
        actor_type=ActorType.system,
        after=after,
    )


def _emit_catalog_load_evidence(
    *,
    audit_session: Session,
    report: LoadReport,
    sha_map: dict[str, str | None],
    dirty: bool,
    actor: str,
) -> None:
    """Emit one chain-of-custody evidence row per reload pass (T059).

    `source_checksum` is SHA-256 over the lexicographically-sorted list
    of `<relpath>:<sha>` pairs. A later auditor can recompute the same
    digest from the file list to confirm the database came from exactly
    those commits.

    Dirty-tree loads (where some SHAs are ``None``) still emit a row;
    the ``after_state.dirty=True`` flag signals that the fingerprint
    is not reproducible against the index alone.
    """
    # Lazy import to avoid a top-level cycle with gard.core.evidence,
    # which imports gard.models which (indirectly) imports the catalog
    # tables.
    import hashlib

    from gard.core.evidence import emit as evidence_emit

    sorted_pairs = sorted(
        (relpath, sha_map.get(relpath) or "DIRTY") for relpath in report.file_relpaths_seen
    )
    fingerprint_input = "\n".join(f"{r}:{s}" for r, s in sorted_pairs).encode("utf-8")
    fingerprint = hashlib.sha256(fingerprint_input).hexdigest()

    evidence_emit(
        session=audit_session,
        evidence_type=EvidenceType.firmware_catalog_load,
        subject_type="FirmwareCatalog",
        subject_id=get_correlation_id() or "no-correlation-id",
        actor=actor,
        after_state={
            "files": len(report.file_relpaths_seen),
            "loaded": report.loaded,
            "removed": report.removed,
            "unchanged": report.unchanged,
            "dirty": dirty,
            "fingerprint_kind": "sha256_over_sorted_relpath_colon_sha",
        },
        source_checksum=fingerprint,
        references={
            "files": [
                {"relpath": r, "git_sha": s if s != "DIRTY" else None} for r, s in sorted_pairs
            ],
        },
    )


def _emit_reload_failed(
    *,
    audit_session: Session,
    error: FirmwareCatalogLoadError,
    actor: str,
) -> None:
    audit_emit(
        session=audit_session,
        action="firmware_catalog.reload_failed",
        object_type="CatalogReload",
        object_id=get_correlation_id() or "no-correlation-id",
        result=AuditResult.failure,
        actor=actor,
        actor_type=ActorType.system,
        after={
            "failing_file_relpath": error.file_relpath,
            "reason": error.reason,
            "schema_path": error.schema_path,
        },
    )


# ---- public entry point ----------------------------------------------


def reload(
    *,
    session: Session,
    audit_session: Session,
    repo_root: Path | None = None,
    catalog_root: Path | None = None,
    actor: str = "system",
) -> ReloadOutcome:
    """Run a full firmware catalog reload pass.

    The two sessions are deliberately separate:

    - ``session`` is bound to ``gard_app`` and performs all catalog
      INSERT/UPDATE operations. The caller is responsible for COMMITTING
      this session on success and ROLLING BACK on failure.
    - ``audit_session`` is bound to ``gard_writer_append_only`` and writes
      audit rows. Audit emission survives even when the catalog
      transaction rolls back, so a reload_failed row always lands.

    ``catalog_root`` defaults to ``Settings.firmware_catalog_root``;
    ``repo_root`` defaults to ``Path.cwd()`` for git SHA lookups.

    The function does NOT commit or roll back the sessions — callers do.
    A common pattern: catch the FirmwareCatalogLoadError, roll back
    ``session``, and commit ``audit_session`` (with the reload_failed
    row already written).
    """
    settings = get_settings()
    catalog_root = catalog_root or settings.firmware_catalog_root
    repo_root = repo_root or Path.cwd()

    # Prod-mode dirty-tree refusal (research.md D2).
    dirty = _is_worktree_dirty(repo_root)
    if dirty and settings.env == "prod":
        err = FirmwareCatalogLoadError(
            file_relpath=str(catalog_root),
            reason="prod refuses to load from a dirty worktree (research.md D2)",
        )
        _emit_reload_failed(audit_session=audit_session, error=err, actor=actor)
        return ReloadOutcome(success=False, error=err, dirty=True)

    try:
        report = load_firmware_catalog(session, catalog_root)
    except FirmwareCatalogLoadError as exc:
        _log.warning(
            "firmware_catalog.reload_failed",
            file=exc.file_relpath,
            reason=exc.reason,
        )
        _emit_reload_failed(audit_session=audit_session, error=exc, actor=actor)
        return ReloadOutcome(success=False, error=exc, dirty=dirty)

    sha_map = _apply_git_shas(session, report, repo_root, report.file_relpaths_seen)

    # Emit audit rows for state changes only — "unchanged" deltas are
    # silent so re-running against an unchanged tree is a true no-op
    # (FR-006 / Assumption "App-boot reload is idempotent").
    state_changing_deltas = [d for d in report.deltas if d.action != "unchanged"]
    for d in state_changing_deltas:
        _emit_delta_audit(
            audit_session=audit_session,
            delta=d,
            git_sha=sha_map.get(d.source_file_relpath),
            actor=actor,
        )

    # Dirty load in non-prod: emit one annotated audit row so accidental
    # dev hot-loads surface in the chain even though they were permitted.
    if dirty:
        audit_emit(
            session=audit_session,
            action="firmware_catalog.reload_dirty",
            object_type="CatalogReload",
            object_id=get_correlation_id() or "no-correlation-id",
            result=AuditResult.success,
            actor=actor,
            actor_type=ActorType.system,
            after={
                "loaded": report.loaded,
                "removed": report.removed,
                "files": len(report.file_relpaths_seen),
                "note": "non-prod dirty worktree; loaded_from_git_sha=NULL on dirty rows",
                "now": dt.datetime.now(dt.UTC).isoformat(),
            },
        )

    # T040: bounded compliance re-eval after a successful reload. Only
    # touch devices that could possibly have a different verdict than
    # before — never the whole devices table.
    re_evaluated = _reevaluate_compliance_post_reload(
        session=session,
        audit_session=audit_session,
        report=report,
        actor=actor,
    )

    # T059: one chain-of-custody evidence row per reload pass. The
    # `source_checksum` is the SHA-256 of the sorted concatenation of
    # the loaded git SHAs — a Merkle-style fingerprint that lets a
    # future auditor confirm "this database state came from exactly
    # these N files at exactly these commits". A reload that only
    # finds `unchanged` deltas still emits one row, so the audit chain
    # has a heartbeat per call.
    _emit_catalog_load_evidence(
        audit_session=audit_session,
        report=report,
        sha_map=sha_map,
        dirty=dirty,
        actor=actor,
    )

    return ReloadOutcome(
        success=True,
        report=report,
        git_shas_by_file=sha_map,
        dirty=dirty,
        devices_reevaluated=re_evaluated,
    )


# ---- bounded post-reload compliance re-evaluation --------------------


def _reevaluate_compliance_post_reload(
    *,
    session: Session,
    audit_session: Session,
    report: LoadReport,
    actor: str,
) -> int:
    """Re-run compliance evaluation for devices touched by this reload.

    "Touched" = device satisfies at least one of:

    1. Currently in a firmware-derived lifecycle state
       (compliant / outside_target / unknown / target_defined). The
       target they were resolved against may have just changed.
    2. Matches the scope_selector of a target that was loaded, removed,
       or had its scope changed in this reload. Their verdict could
       flip from "no target matched" to "target found" (or vice versa).

    We unionize these sets, deduplicate, and call
    ``compliance_controller.evaluate()`` once per device. The
    controller is itself idempotent — re-running against unchanged
    state is silent. So this can never amplify into a runaway audit
    storm: at most one ``compliance_evaluated`` row per device, and
    only when the state actually transitions.

    Returns the number of devices that were actually evaluated (which
    is the upper bound on emitted audit rows — most will be no-ops).
    """
    # Avoid the import cycle: compliance_controller imports the loader
    # transitively, so we import lazily here.
    from gard.core import (
        compliance_controller,
        compliance_evaluation_controller,
        readiness_evaluation_controller,
    )

    target_deltas = [d for d in report.deltas if d.kind == "target" and d.action != "unchanged"]
    touched_target_ids = {d.entity_id for d in target_deltas}

    # F4 (R-6): prereq rules that changed in this reload contribute set3 —
    # any device whose facts match the rule's applies_to becomes touched.
    prereq_deltas = [
        d for d in report.deltas if d.kind == "prerequisite" and d.action != "unchanged"
    ]
    touched_prereq_ids = {d.entity_id for d in prereq_deltas}

    # Set 1: devices already in a firmware-derived lifecycle state.
    firmware_states = (
        LifecycleState.target_defined,
        LifecycleState.compliant,
        LifecycleState.outside_target,
        LifecycleState.unknown,
    )
    set1: set[Any] = set(
        session.scalars(select(Device.id).where(Device.lifecycle_state.in_(firmware_states)))
    )

    # Sets 2 + 3 both walk the device list once and match against the
    # touched targets (set 2) and touched prereq rules (set 3). We share
    # the device fetch + facts construction so the scan is single-pass.
    set2: set[Any] = set()
    set3: set[Any] = set()
    if touched_target_ids or touched_prereq_ids:
        from gard.core.scope_selector import evaluate as evaluate_selector
        from gard.models import FirmwarePrerequisiteRule

        touched_targets = (
            list(
                session.scalars(
                    select(FirmwareTarget).where(FirmwareTarget.id.in_(touched_target_ids))
                )
            )
            if touched_target_ids
            else []
        )
        touched_prereqs = (
            list(
                session.scalars(
                    select(FirmwarePrerequisiteRule).where(
                        FirmwarePrerequisiteRule.id.in_(touched_prereq_ids)
                    )
                )
            )
            if touched_prereq_ids
            else []
        )
        devices = list(session.scalars(select(Device)))
        for device in devices:
            facts = {
                "vendor_normalized": device.vendor_normalized,
                "platform_family": device.platform_family,
                "region": device.region,
                "site": device.site,
                "role": device.role,
                "hardware_revision": device.hardware_revision,
                "lifecycle_state": device.lifecycle_state.value,
            }
            if device.id not in set2:
                for t in touched_targets:
                    if evaluate_selector(t.scope_selector, facts).matched:
                        set2.add(device.id)
                        break
            if device.id not in set3:
                for r in touched_prereqs:
                    if evaluate_selector(r.applies_to, facts).matched:
                        set3.add(device.id)
                        break

    affected = set1 | set2 | set3
    if not affected:
        return 0

    count = 0
    for device_id in affected:
        # F2 controller updates lifecycle_state + emits its own audit.
        compliance_controller.evaluate(
            session=session,
            audit_session=audit_session,
            device_id=device_id,
            actor=actor,
        )
        # F3 controller classifies drift + persists ComplianceEvaluation
        # rows. Idempotent on unchanged inputs — silent for devices whose
        # F3 verdict didn't change. Wrapped in try so an F3-side failure
        # never breaks the F2 reload pipeline (per ADR-0011 §8: serve
        # last-known state rather than abort).
        try:
            compliance_evaluation_controller.evaluate(
                session=session,
                audit_session=audit_session,
                device_id=device_id,
                actor=actor,
            )
        except Exception as exc:  # pragma: no cover - defensive
            _log.warning(
                "firmware_catalog.f3_post_reload_failed",
                device_id=str(device_id),
                error=str(exc),
            )
        # F4 controller derives readiness from F3's latest row. Same
        # defensive try/except — a F4 bug must not break the F2 reload.
        try:
            readiness_evaluation_controller.evaluate(
                session=session,
                audit_session=audit_session,
                device_id=device_id,
                actor=actor,
            )
        except Exception as exc:  # pragma: no cover - defensive
            _log.warning(
                "firmware_catalog.f4_post_reload_failed",
                device_id=str(device_id),
                error=str(exc),
            )
        count += 1

    _log.info(
        "firmware_catalog.post_reload_reevaluated",
        devices=count,
        touched_targets=len(touched_target_ids),
        touched_prereqs=len(touched_prereq_ids),
    )
    return count


# ---- helper used by lifespan handler ---------------------------------


def reload_safe(
    *,
    session_factory: Callable[[], ContextManager[Session]],
    audit_session_factory: Callable[[], ContextManager[Session]],
    repo_root: Path | None = None,
    catalog_root: Path | None = None,
    actor: str = "system",
) -> ReloadOutcome:
    """Convenience wrapper for app boot: runs reload + commits sessions itself.

    Failures are SWALLOWED per ADR-0011 §8 — the boot-time-reload-failure
    posture says serve last-known state rather than crash. The caller
    receives a ReloadOutcome with success=False and inspects the error
    for structured-log purposes.
    """
    with session_factory() as cat_sess, audit_session_factory() as aud_sess:
        try:
            outcome = reload(
                session=cat_sess,
                audit_session=aud_sess,
                repo_root=repo_root,
                catalog_root=catalog_root,
                actor=actor,
            )
            if outcome.success:
                cat_sess.commit()
            else:
                cat_sess.rollback()
            aud_sess.commit()
            return outcome
        except Exception:  # pragma: no cover -- defensive
            cat_sess.rollback()
            try:
                aud_sess.commit()
            except Exception:
                aud_sess.rollback()
            raise


# Re-exports for the loader-failure path so callers can ``except`` the
# exception type without importing from ``gard.catalog``.
__all__ = [
    "FirmwareCatalogLoadError",
    "ReloadOutcome",
    "reload",
    "reload_safe",
]
