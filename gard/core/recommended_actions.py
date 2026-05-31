"""Builders for F3's typed RecommendedAction vocabulary.

Each public function emits exactly one :class:`RecommendedAction` for
a specific drift type. Composition is the caller's job — the
controller takes the active drift set, calls the right builders, and
sorts the result deterministically (ADR-0014, R-7).

The ``requires`` field on each action names the RBAC permission an
actor needs to *execute* the suggestion. UIs render actions for which
the caller holds the permission as buttons; others as text.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from gard.core.envelope import (
    DriftType,
    FirmwareComplianceEnvelope,
    RecommendedAction,
)
from gard.core.rbac import Permission

if False:  # pragma: no cover - typing only
    from gard.models import Device


# ---- per-kind builders ---------------------------------------------------


def upgrade_path_query(
    *,
    device_id: uuid.UUID,
    target_version: str,
    target_platform_family: str | None,
) -> RecommendedAction:
    """target_drift / rule_drift: ask F4 for an upgrade plan."""
    return RecommendedAction(
        kind="upgrade_path_query",
        target_device_id=str(device_id),
        target_version=target_version,
        target_platform_family=target_platform_family,
        requires=[Permission.READ_FIRMWARE_CATALOG],
        detail=(f"query upgrade-path graph for a chain to {target_version!r}"),
    )


def define_target(
    *,
    device_id: uuid.UUID,
    platform_family: str | None,
) -> RecommendedAction:
    """catalog_drift: catalog owner needs to author a target row."""
    return RecommendedAction(
        kind="define_target",
        target_device_id=str(device_id),
        target_platform_family=platform_family,
        requires=[Permission.MANAGE_RULES],
        detail=(
            "add a FirmwareTarget YAML under gard-catalog/firmware/targets/ "
            "whose scope_selector matches this device's facts, then "
            "`make catalog-reload`"
        ),
    )


def define_upgrade_path(
    *,
    observed_version: str | None,
    target_version: str,
    target_platform_family: str | None,
) -> RecommendedAction:
    """rule_drift: catalog owner must author an upgrade-path edge."""
    return RecommendedAction(
        kind="define_upgrade_path",
        target_version=target_version,
        target_platform_family=target_platform_family,
        requires=[Permission.MANAGE_RULES],
        detail=(
            f"add FirmwareUpgradePath edges that reach {target_version!r} "
            f"from {observed_version!r} on this platform"
        ),
    )


def upload_firmware_package(
    *,
    target_version: str,
    target_firmware_target_id: str | None,
    target_platform_family: str | None,
) -> RecommendedAction:
    """package_drift: catalog owner needs to upload the blob."""
    return RecommendedAction(
        kind="upload_firmware_package",
        target_version=target_version,
        target_firmware_target_id=target_firmware_target_id,
        target_platform_family=target_platform_family,
        requires=[Permission.MANAGE_FIRMWARE_BLOB],
        detail=(f"POST /api/v1/firmware/packages/{{id}}/blob for version {target_version!r}"),
    )


def trigger_discovery(*, device_id: uuid.UUID) -> RecommendedAction:
    """discovery_drift: kick the discovery agent."""
    return RecommendedAction(
        kind="trigger_discovery",
        target_device_id=str(device_id),
        requires=[Permission.IMPORT_DEVICES],
        detail=(
            "schedule a discovery/refresh job for this device — current "
            "observation is missing or stale"
        ),
    )


def request_observation_refresh(
    *,
    device_id: uuid.UUID,
    observation_id: uuid.UUID | None,
) -> RecommendedAction:
    """evidence_drift: ask for a re-validation pass."""
    return RecommendedAction(
        kind="request_observation_refresh",
        target_device_id=str(device_id),
        target_observation_id=str(observation_id) if observation_id else None,
        requires=[Permission.REEVALUATE_OBSERVATION],
        detail=("re-run a re_evaluation pass so this device emits a fresh lifecycle_evidence row"),
    )


def escalate_to_catalog_owner(
    *,
    device_id: uuid.UUID,
    detail: str,
) -> RecommendedAction:
    """Fallback escalation when no specific repair action applies."""
    return RecommendedAction(
        kind="escalate_to_catalog_owner",
        target_device_id=str(device_id),
        requires=[],
        detail=detail,
    )


# ---- F4 builders (readiness & prerequisites) ----------------------------


def schedule_uplift_wave(
    *,
    device_id: uuid.UUID,
    target_version: str | None,
    target_platform_family: str | None,
) -> RecommendedAction:
    """ready_for_uplift: F5's primary input."""
    return RecommendedAction(
        kind="schedule_uplift_wave",
        target_device_id=str(device_id),
        target_version=target_version,
        target_platform_family=target_platform_family,
        requires=[Permission.READ_READINESS],
        detail=(
            f"device is ready for uplift to {target_version!r}; queue "
            f"for the next wave"
        ),
    )


def hardware_refresh(
    *,
    device_id: uuid.UUID,
    detail: str,
) -> RecommendedAction:
    """min_ram_mb / min_disk_mb / hardware_revision_in: physical refresh."""
    return RecommendedAction(
        kind="hardware_refresh",
        target_device_id=str(device_id),
        requires=[],
        detail=detail,
    )


def license_acquire(
    *,
    device_id: uuid.UUID,
    detail: str,
) -> RecommendedAction:
    """license_present blocker: procurement work."""
    return RecommendedAction(
        kind="license_acquire",
        target_device_id=str(device_id),
        requires=[],
        detail=detail,
    )


def firmware_intermediate_step(
    *,
    device_id: uuid.UUID,
    target_version: str | None,
    target_platform_family: str | None,
    detail: str,
) -> RecommendedAction:
    """intermediate_version_required OR missing_upgrade_path blockers."""
    return RecommendedAction(
        kind="firmware_intermediate_step",
        target_device_id=str(device_id),
        target_version=target_version,
        target_platform_family=target_platform_family,
        requires=[Permission.READ_FIRMWARE_CATALOG],
        detail=detail,
    )


def import_observation(
    *,
    device_id: uuid.UUID,
    detail: str,
) -> RecommendedAction:
    """missing_observation_field blocker: F1/F7 data-hygiene work."""
    return RecommendedAction(
        kind="import_observation",
        target_device_id=str(device_id),
        requires=[Permission.IMPORT_DEVICES],
        detail=detail,
    )


# ---- top-level composer --------------------------------------------------


def build_actions_for(
    *,
    device: Device,
    envelope: FirmwareComplianceEnvelope,
    drifts: Iterable[DriftType],
) -> list[RecommendedAction]:
    """Produce a sorted list of actions for the active drift set.

    Sort order: by ``RecommendedActionKind`` enum order, then by the
    JSON serialisation of the action — deterministic so the response
    envelope is byte-stable across calls with identical inputs
    (SC-005).

    The controller passes the F2 envelope (target_ref, target_version,
    observed_version) plus the set of drift types that fired. Drift
    types not in this function's mapping (e.g. ``exception_drift``
    which is a v1 no-op) contribute no actions.
    """
    actions: list[RecommendedAction] = []
    drift_set = set(drifts)

    if "catalog_drift" in drift_set:
        actions.append(
            define_target(
                device_id=device.id,
                platform_family=device.platform_family,
            )
        )

    if "rule_drift" in drift_set and envelope.target_version is not None:
        actions.append(
            define_upgrade_path(
                observed_version=envelope.observed_version,
                target_version=envelope.target_version,
                target_platform_family=device.platform_family,
            )
        )

    if "package_drift" in drift_set and envelope.target_version is not None:
        actions.append(
            upload_firmware_package(
                target_version=envelope.target_version,
                target_firmware_target_id=envelope.target_ref,
                target_platform_family=device.platform_family,
            )
        )

    if (
        "target_drift" in drift_set
        and envelope.target_version is not None
        and "rule_drift" not in drift_set
    ):
        # When rule_drift fires, define_upgrade_path is the more useful
        # action; the upgrade_path_query would just return "no path".
        actions.append(
            upgrade_path_query(
                device_id=device.id,
                target_version=envelope.target_version,
                target_platform_family=device.platform_family,
            )
        )

    if "discovery_drift" in drift_set:
        actions.append(trigger_discovery(device_id=device.id))

    if "evidence_drift" in drift_set:
        actions.append(
            request_observation_refresh(
                device_id=device.id,
                observation_id=None,
            )
        )

    # Stable sort: by kind, then JSON repr of the payload.
    return sorted(actions, key=lambda a: (a.kind, a.model_dump_json()))
