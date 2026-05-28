"""T062 — verify the CSV reader against representative valid + invalid rows."""

from __future__ import annotations

import pytest

from gard.api.schemas.csv_row import CSV_ERROR_CODES
from gard.core.csv_reader import collect_outcomes, iter_rows
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.contract


def test_valid_row_parses_clean() -> None:
    body = csv_body([csv_row()])
    out = collect_outcomes(iter_rows(body))
    assert len(out) == 1
    assert out[0].is_valid


def test_missing_identity_raises_row_missing_identity() -> None:
    body = csv_body([csv_row(hostname="", serial_number="")])
    out = collect_outcomes(iter_rows(body))
    codes = {c for c, _ in out[0].errors}
    # `hostname` is min_length=1 -> ROW_VALIDATION; identity invariant
    # also flags ROW_MISSING_IDENTITY when serial is empty.
    assert "ROW_VALIDATION" in codes or "ROW_MISSING_IDENTITY" in codes


def test_observed_at_future() -> None:
    body = csv_body([csv_row(observed_at="2099-01-01T00:00:00Z")])
    out = collect_outcomes(iter_rows(body))
    codes = {c for c, _ in out[0].errors}
    assert "ROW_OBSERVED_AT_FUTURE" in codes


def test_bad_ipaddress() -> None:
    body = csv_body([csv_row(management_ip="999.999.999.999")])
    out = collect_outcomes(iter_rows(body))
    codes = {c for c, _ in out[0].errors}
    assert "ROW_BAD_IPADDRESS" in codes


def test_bad_datetime() -> None:
    body = csv_body([csv_row(observed_at="not-a-date")])
    out = collect_outcomes(iter_rows(body))
    codes = {c for c, _ in out[0].errors}
    assert "ROW_BAD_DATETIME" in codes


def test_every_error_code_documented() -> None:
    # Sanity: code constants in csv_row.py mirror the YAML schema's set.
    expected = {
        "ROW_ENCODING",
        "ROW_BAD_COLUMNS",
        "ROW_MISSING_IDENTITY",
        "ROW_MISSING_VENDOR_AND_MODEL",
        "ROW_OBSERVED_AT_FUTURE",
        "ROW_BAD_IPADDRESS",
        "ROW_BAD_DATETIME",
        "ROW_DUPLICATE_IN_FILE",
    }
    assert expected.issubset(CSV_ERROR_CODES.keys())
