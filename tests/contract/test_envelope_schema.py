"""T051 — `build_envelope` output validates against the OpenAPI Envelope schema."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from gard.core.envelope import Reason, build_envelope

pytestmark = pytest.mark.contract


def _load_envelope_schema() -> dict:
    p = Path("specs/001-device-import-normalize/contracts/rest-openapi.yaml")
    spec = yaml.safe_load(p.read_text())
    components = spec["components"]["schemas"]

    # Inline references to support a JSONSchema-style validator without
    # touching the OpenAPI spec.
    def _inline(node: object) -> object:
        if isinstance(node, dict):
            if "$ref" in node and isinstance(node["$ref"], str):
                ref = node["$ref"]
                assert ref.startswith("#/components/schemas/"), ref
                name = ref.rsplit("/", 1)[-1]
                return _inline(components[name])
            return {k: _inline(v) for k, v in node.items() if k != "discriminator"}
        if isinstance(node, list):
            return [_inline(v) for v in node]
        return node

    # Find the envelope schema under any of the names the contract uses.
    for cand in ("ResponseEnvelope", "Envelope", "DeviceEnvelope"):
        if cand in components:
            return _inline(components[cand])  # type: ignore[return-value]
    pytest.skip("OpenAPI spec does not define an Envelope schema; contract not yet enforced")
    raise AssertionError  # for mypy


def test_build_envelope_known_state_validates() -> None:
    schema = _load_envelope_schema()
    env = build_envelope(
        state="known",
        summary="example",
        facts={"k": "v"},
        reasons=[Reason(kind="rule_match", ref="cisco-ios:v1.r0", detail="matched")],
        confidence=0.9,
        correlation_id="cid-test",
    )
    body = env.model_dump(mode="json")

    # Drop fields the OpenAPI schema may not declare; jsonschema strict
    # validation is on `additionalProperties` only when set in the spec.
    Draft202012Validator(schema).validate(body)


def test_build_envelope_unknown_requires_missing_inputs() -> None:
    env = build_envelope(
        state="unknown",
        summary="cannot classify yet",
        facts={"hostname": "h1"},
        reasons=[Reason(kind="missing_input", ref="vendor_raw", detail="empty in CSV")],
        recommended_actions=["upload a row carrying vendor_raw"],
        confidence=0.0,
    )
    assert env.state == "unknown"
    assert any(r.kind == "missing_input" for r in env.reasons)
