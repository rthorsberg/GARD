"""T052 — every response carries `X-Correlation-Id`."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.contract


def test_health_emits_correlation_id(client) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.headers.get("x-correlation-id"), r.headers


def test_health_preserves_incoming_correlation_id(client) -> None:
    cid = str(uuid.uuid4())
    r = client.get("/healthz", headers={"X-Correlation-Id": cid})
    assert r.status_code == 200
    assert r.headers.get("x-correlation-id") == cid


def test_error_envelope_includes_correlation_id(client) -> None:
    cid = "deadbeef-cafe-1234"
    r = client.get("/api/v1/audit", headers={"X-Correlation-Id": cid})
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["correlation_id"] == cid
    assert r.headers.get("x-correlation-id") == cid
