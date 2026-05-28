"""`normalization_rules` — DB rules (overrides + mirrored YAML)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow
from gard.models._enums import Confidence, RuleSource


class NormalizationRule(Base):
    __tablename__ = "normalization_rules"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    match: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Confidence] = mapped_column(
        Enum(Confidence, name="rule_confidence", native_enum=False, length=32),
        nullable=False,
    )
    source: Mapped[RuleSource] = mapped_column(
        Enum(RuleSource, name="rule_source", native_enum=False, length=8),
        nullable=False,
    )
    source_path: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    exported_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )
