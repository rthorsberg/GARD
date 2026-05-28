"""Streaming CSV reader (T071).

Yields ``(row_number, row_dict, errors)`` tuples. Row 1 is the header
row; data rows start at 2. Errors are ``(code, message)`` tuples — see
:data:`gard.api.schemas.csv_row.CSV_ERROR_CODES`.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO, Any

from pydantic import ValidationError

from gard.api.schemas.csv_row import REQUIRED_COLUMNS, CsvRow, row_invariants


@dataclass(frozen=True)
class RowOutcome:
    """One parsed CSV row with its validation result."""

    row_number: int
    raw: dict[str, Any]
    parsed: CsvRow | None
    errors: list[tuple[str, str]]

    @property
    def is_valid(self) -> bool:
        return self.parsed is not None and not self.errors


class CsvReaderError(ValueError):
    """Raised before the first data row when the CSV cannot be parsed at all."""


def _decode(stream: IO[bytes] | bytes | str) -> io.StringIO:
    if isinstance(stream, str):
        return io.StringIO(stream)
    if isinstance(stream, bytes):
        try:
            return io.StringIO(stream.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise CsvReaderError(f"file is not valid UTF-8: {exc}") from exc
    raw = stream.read()
    try:
        return io.StringIO(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CsvReaderError(f"file is not valid UTF-8: {exc}") from exc


def _normalize_header(h: str) -> str:
    return h.strip().lower()


def iter_rows(stream: IO[bytes] | bytes | str) -> Iterator[RowOutcome]:
    """Stream rows out of a CSV byte/string source."""
    text_stream = _decode(stream)
    reader = csv.reader(text_stream, delimiter=",", quotechar='"')
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise CsvReaderError("empty CSV (no header)") from exc

    header = [_normalize_header(c) for c in raw_header]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise CsvReaderError(f"missing required header columns: {', '.join(missing)}")

    seen: set[str] = set()
    duplicates: list[str] = []
    for h in header:
        if h in seen:
            duplicates.append(h)
        seen.add(h)
    if duplicates:
        raise CsvReaderError(f"duplicate header columns: {', '.join(duplicates)}")

    for row_number, raw_cells in enumerate(reader, start=2):
        errs: list[tuple[str, str]] = []
        if len(raw_cells) != len(header):
            yield RowOutcome(
                row_number=row_number,
                raw={"__raw_cells__": raw_cells},
                parsed=None,
                errors=[
                    (
                        "ROW_BAD_COLUMNS",
                        f"row has {len(raw_cells)} cells, header has {len(header)}",
                    )
                ],
            )
            continue

        row_map: dict[str, Any] = {h: c for h, c in zip(header, raw_cells, strict=True)}

        try:
            parsed = CsvRow.model_validate(row_map)
        except ValidationError as exc:
            for e in exc.errors():
                # Bad datetime gets a stable code so reports stay machine-readable.
                if e.get("type") == "datetime_from_date_parsing" or (
                    e.get("loc") and e["loc"][0] == "observed_at"
                ):
                    errs.append(("ROW_BAD_DATETIME", str(e.get("msg") or e)))
                else:
                    errs.append(("ROW_VALIDATION", _fmt_pydantic_err(e)))
            yield RowOutcome(
                row_number=row_number,
                raw=row_map,
                parsed=None,
                errors=errs,
            )
            continue

        errs.extend(row_invariants(parsed))

        yield RowOutcome(
            row_number=row_number,
            raw=row_map,
            parsed=parsed if not errs else None,
            errors=errs,
        )


def _fmt_pydantic_err(e: Any) -> str:
    loc = ".".join(
        str(p) for p in (e.get("loc") if isinstance(e, dict) else getattr(e, "loc", ())) or ()
    )
    msg = e.get("msg", "") if isinstance(e, dict) else getattr(e, "msg", "")
    return f"{loc}: {msg}"


def collect_outcomes(rows: Iterable[RowOutcome]) -> list[RowOutcome]:
    """Eager helper used by tests / sync imports."""
    return list(rows)
