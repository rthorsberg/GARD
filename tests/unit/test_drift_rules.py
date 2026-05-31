"""Truth-table tests for each F3 drift rule.

Pure-function tests: every rule is exercised with one positive case
(rule fires) and one negative case (rule does NOT fire). No DB needed
— the rules consume already-loaded data, not sessions.

Rules covered: target / catalog / package / rule / discovery / evidence
/ exception. Each rule's two-row truth table is below.
"""

from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace

from gard.core import drift_rules
from gard.core.envelope import (
    FirmwareComplianceReason,
    build_firmware_compliance_envelope,
)


def _env(
    *,
    state: str,
    target_version: str | None = None,
    observed_version: str | None = None,
    target_ref: str | None = None,
    reasons: list[FirmwareComplianceReason] | None = None,
):
    """Build a minimal F2 envelope for drift-rule input."""
    return build_firmware_compliance_envelope(
        state=state,  # type: ignore[arg-type]
        summary="-",
        target_ref=target_ref,
        target_version=target_version,
        observed_version=observed_version,
        reasons=reasons or [],
    )


# ---- target_drift -------------------------------------------------------


def test_target_drift_fires_when_outside_target() -> None:
    env = _env(
        state="outside_target",
        target_version="7.8.1",
        observed_version="7.5.2",
        target_ref=str(uuid.uuid4()),
    )
    reason = drift_rules.is_target_drift(env)
    assert reason is not None
    assert reason.kind == "version_mismatch"


def test_target_drift_silent_when_compliant() -> None:
    env = _env(state="compliant", target_version="7.8.1", observed_version="7.8.1")
    assert drift_rules.is_target_drift(env) is None


# ---- catalog_drift ------------------------------------------------------


def test_catalog_drift_fires_when_no_target_matched() -> None:
    env = _env(
        state="classified",
        reasons=[FirmwareComplianceReason(kind="no_target_matched", detail="-")],
    )
    reason = drift_rules.is_catalog_drift(env)
    assert reason is not None
    assert reason.kind == "no_target_matched"


def test_catalog_drift_silent_when_target_resolved() -> None:
    env = _env(
        state="outside_target",
        target_version="7.8.1",
        observed_version="7.5.2",
    )
    assert drift_rules.is_catalog_drift(env) is None


# ---- package_drift ------------------------------------------------------


def test_package_drift_fires_when_no_package_row_exists() -> None:
    env = _env(state="outside_target", target_version="7.8.1", observed_version="7.5.2")
    reason = drift_rules.is_package_drift(env, package=None)
    assert reason is not None
    assert reason.kind == "package_not_built"
    assert "no FirmwarePackage row" in (reason.detail or "")


def test_package_drift_silent_when_package_with_blob_exists() -> None:
    env = _env(state="outside_target", target_version="7.8.1", observed_version="7.5.2")
    pkg = SimpleNamespace(id=uuid.uuid4(), blob_present=True)
    assert drift_rules.is_package_drift(env, package=pkg) is None  # type: ignore[arg-type]


def test_package_drift_fires_when_package_without_blob() -> None:
    env = _env(state="outside_target", target_version="7.8.1", observed_version="7.5.2")
    pkg = SimpleNamespace(id=uuid.uuid4(), blob_present=False)
    reason = drift_rules.is_package_drift(env, package=pkg)  # type: ignore[arg-type]
    assert reason is not None
    assert "blob_present=false" in (reason.detail or "")


# ---- rule_drift ---------------------------------------------------------


def test_rule_drift_fires_when_no_upgrade_paths_exist() -> None:
    env = _env(state="outside_target", target_version="7.8.1", observed_version="7.5.2")
    reason = drift_rules.is_rule_drift(env, upgrade_paths_exist=False)
    assert reason is not None
    assert reason.kind == "missing_upgrade_path"


def test_rule_drift_silent_when_paths_exist() -> None:
    env = _env(state="outside_target", target_version="7.8.1", observed_version="7.5.2")
    assert drift_rules.is_rule_drift(env, upgrade_paths_exist=True) is None


# ---- discovery_drift ----------------------------------------------------


def test_discovery_drift_fires_for_missing_observation() -> None:
    env = _env(state="unknown")
    now = dt.datetime.now(dt.UTC)
    reason = drift_rules.is_discovery_drift(
        env, latest_observation=None, now=now, stale_after_days=30
    )
    assert reason is not None
    assert reason.kind == "missing_observation"


def test_discovery_drift_fires_for_stale_observation() -> None:
    env = _env(state="compliant", target_version="7.8.1", observed_version="7.8.1")
    now = dt.datetime.now(dt.UTC)
    stale_obs = SimpleNamespace(
        id=uuid.uuid4(),
        observed_at=now - dt.timedelta(days=60),
    )
    reason = drift_rules.is_discovery_drift(
        env,
        latest_observation=stale_obs,
        now=now,
        stale_after_days=30,  # type: ignore[arg-type]
    )
    assert reason is not None
    assert reason.kind == "stale_observation"


def test_discovery_drift_silent_for_fresh_observation() -> None:
    env = _env(state="compliant", target_version="7.8.1", observed_version="7.8.1")
    now = dt.datetime.now(dt.UTC)
    fresh_obs = SimpleNamespace(
        id=uuid.uuid4(),
        observed_at=now - dt.timedelta(days=2),
    )
    assert (
        drift_rules.is_discovery_drift(
            env,
            latest_observation=fresh_obs,
            now=now,
            stale_after_days=30,  # type: ignore[arg-type]
        )
        is None
    )


# ---- evidence_drift -----------------------------------------------------


def test_evidence_drift_fires_for_compliant_with_no_reeval_evidence() -> None:
    env = _env(state="compliant", target_version="7.8.1", observed_version="7.8.1")
    reason = drift_rules.is_evidence_drift(
        env,
        latest_reeval_evidence_at=None,
        now=dt.datetime.now(dt.UTC),
        stale_after_days=90,
    )
    assert reason is not None


def test_evidence_drift_silent_when_not_compliant() -> None:
    env = _env(state="outside_target", target_version="7.8.1", observed_version="7.5.2")
    assert (
        drift_rules.is_evidence_drift(
            env,
            latest_reeval_evidence_at=None,
            now=dt.datetime.now(dt.UTC),
            stale_after_days=90,
        )
        is None
    )


# ---- exception_drift ----------------------------------------------------


def test_exception_drift_always_silent_in_v1() -> None:
    """ADR-0014: F5 forward seam, v1 never fires."""
    env = _env(state="compliant", target_version="7.8.1", observed_version="7.8.1")
    assert drift_rules.is_exception_drift(env) is None
