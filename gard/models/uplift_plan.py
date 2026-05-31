"""`uplift_plans` — top-level grouping for uplift waves (F5).

A plan is a free-form operator label that groups one or more waves
(e.g. "Q3 2026 EU North uplift"). Plans carry no device list and no
state machine beyond `archived_at`. Devices belong to waves.

Plans are append-only at the row level — there is no UPDATE that
mutates an existing wave's `plan_id`. Archival is a soft delete:
`archived_at IS NOT NULL` hides the plan from default listings.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class UpliftPlan(Base):
    __tablename__ = "uplift_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "length(name) BETWEEN 1 AND 200",
            name="ck_uplift_plans_name_len",
        ),
        CheckConstraint(
            "(archived_at IS NULL) = (archived_by IS NULL)",
            name="ck_uplift_plans_archived_pair",
        ),
        Index(
            "ix_uplift_plans_created_at_desc",
            text("created_at DESC"),
        ),
        Index(
            "uq_uplift_plans_name_active",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        archived = " archived" if self.archived_at else ""
        return f"<UpliftPlan id={self.id} name={self.name!r}{archived}>"
