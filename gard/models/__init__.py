"""SQLAlchemy declarative models.

All ORM models inherit from :class:`Base` and use :func:`uuid7_default`
for primary keys so audit/evidence rows and business rows share the same
time-ordered UUID space.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase
from uuid_extensions import uuid7 as _uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid7_default() -> uuid.UUID:
    """Generate a UUID7 (time-ordered) for primary keys.

    SQLAlchemy calls this on the Python side at INSERT time. v1 does not
    rely on a server-side function so we don't have to extend Postgres
    with `pg_uuidv7`.
    """
    value = _uuid7()
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def utcnow() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.UTC)


# Import models so SQLAlchemy registers them on Base.metadata.
from gard.models.api_token import ApiToken  # noqa: E402
from gard.models.audit_event import AuditChainHead, AuditEvent  # noqa: E402
from gard.models.compliance_evaluation import ComplianceEvaluation  # noqa: E402
from gard.models.device import Device  # noqa: E402
from gard.models.firmware_package import FirmwarePackage  # noqa: E402
from gard.models.firmware_prerequisite import (  # noqa: E402
    FirmwarePrerequisiteRule,
    PredicateKind,
    PrereqSeverity,
)
from gard.models.firmware_target import FirmwareTarget  # noqa: E402
from gard.models.firmware_upgrade_path import FirmwareUpgradePath  # noqa: E402
from gard.models.import_job import ImportJob  # noqa: E402
from gard.models.lifecycle_evidence import LifecycleEvidence  # noqa: E402
from gard.models.manual_mapping import ManualMapping  # noqa: E402
from gard.models.normalization_rule import NormalizationRule  # noqa: E402
from gard.models.observation import DeviceObservation  # noqa: E402
from gard.models.readiness_evaluation import ReadinessEvaluation  # noqa: E402
from gard.models.uplift_exception import UpliftException  # noqa: E402
from gard.models.uplift_plan import UpliftPlan  # noqa: E402
from gard.models.uplift_wave import UpliftWave  # noqa: E402
from gard.models.uplift_wave_device import UpliftWaveDevice  # noqa: E402

__all__ = [
    "ApiToken",
    "AuditChainHead",
    "AuditEvent",
    "Base",
    "ComplianceEvaluation",
    "Device",
    "DeviceObservation",
    "FirmwarePackage",
    "FirmwarePrerequisiteRule",
    "FirmwareTarget",
    "FirmwareUpgradePath",
    "ImportJob",
    "LifecycleEvidence",
    "ManualMapping",
    "NormalizationRule",
    "PredicateKind",
    "PrereqSeverity",
    "ReadinessEvaluation",
    "UpliftException",
    "UpliftPlan",
    "UpliftWave",
    "UpliftWaveDevice",
    "utcnow",
    "uuid7_default",
]
