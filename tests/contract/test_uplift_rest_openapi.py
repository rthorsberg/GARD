"""Contract test for F5 REST OpenAPI schema.

Loads ``specs/005-uplift-planning-waves/contracts/rest-openapi.yaml``
and asserts every declared path + method + parameter name is present in
the service's served ``/openapi.json``. F5 paths are relative to the
contract's ``servers[0].url`` (``/api/v1``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from gard.api.app import create_app
from gard.core.rbac import Permission, role_permissions
from gard.models._enums import Role

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "005-uplift-planning-waves"
    / "contracts"
    / "rest-openapi.yaml"
)


def _load_contract_doc() -> dict:
    with CONTRACT.open() as fp:
        return yaml.safe_load(fp)


def _contract_paths() -> dict[str, dict]:
    doc = _load_contract_doc()
    base = doc.get("servers", [{}])[0].get("url", "").rstrip("/")
    raw = doc.get("paths", {})
    return {f"{base}{path}": item for path, item in raw.items()}


@pytest.fixture(scope="module")
def served_schema() -> dict:
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/openapi.json")
        assert r.status_code == 200
        return r.json()


def test_contract_yaml_loads() -> None:
    assert CONTRACT.exists()
    paths = _contract_paths()
    assert len(paths) == 11, f"F5 declares 11 REST paths, got {len(paths)}"


def test_every_contract_path_is_served(served_schema: dict) -> None:
    served_paths = set(served_schema.get("paths", {}).keys())
    contract_paths = set(_contract_paths().keys())
    missing = contract_paths - served_paths
    assert not missing, f"contract paths missing from /openapi.json: {sorted(missing)}"


def test_every_contract_method_is_served(served_schema: dict) -> None:
    served_paths = served_schema.get("paths", {})
    for path, item in _contract_paths().items():
        served_methods = set(served_paths.get(path, {}).keys())
        contract_methods = {m for m in item if m in {"get", "post", "put", "patch", "delete"}}
        missing = contract_methods - served_methods
        assert not missing, (
            f"contract path {path} declares {contract_methods} but served exposes "
            f"{served_methods}; missing {missing}"
        )


def test_path_parameter_names_match(served_schema: dict) -> None:
    served_paths = served_schema.get("paths", {})
    for path, item in _contract_paths().items():
        for method, op in item.items():
            if method not in {"get", "post"}:
                continue
            contract_params = {p["name"] for p in op.get("parameters", [])}
            served_op = served_paths.get(path, {}).get(method, {})
            served_params = {p["name"] for p in served_op.get("parameters", [])}
            missing = contract_params - served_params
            assert not missing, (
                f"{method.upper()} {path}: contract declares parameters "
                f"{contract_params}, served exposes {served_params}; missing {missing}"
            )


def _collect_enum_values(node: object, acc: set[str]) -> None:
    if isinstance(node, dict):
        if "enum" in node and isinstance(node["enum"], list):
            acc.update(v for v in node["enum"] if isinstance(v, str))
        for v in node.values():
            _collect_enum_values(v, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_enum_values(item, acc)


def test_served_schema_includes_f5_wave_states(served_schema: dict) -> None:
    expected = {
        "draft",
        "submitted",
        "approved",
        "rejected",
        "cancelled",
        "invalidated",
    }
    all_enum_values: set[str] = set()
    _collect_enum_values(served_schema.get("components", {}), all_enum_values)
    missing = expected - all_enum_values
    assert not missing, f"served OpenAPI is missing WaveState values: {missing}"


def test_served_schema_includes_f5_exception_states(served_schema: dict) -> None:
    expected = {
        "pending_review",
        "approved",
        "rejected",
        "expired",
        "withdrawn",
    }
    all_enum_values: set[str] = set()
    _collect_enum_values(served_schema.get("components", {}), all_enum_values)
    missing = expected - all_enum_values
    assert not missing, f"served OpenAPI is missing ExceptionState values: {missing}"


def test_served_schema_includes_f5_recommended_action_kinds(served_schema: dict) -> None:
    expected = {
        "submit_for_approval",
        "assign_approver",
        "extend_change_window",
        "request_exception_review",
        "cancel_wave",
    }
    all_enum_values: set[str] = set()
    _collect_enum_values(served_schema.get("components", {}), all_enum_values)
    missing = expected - all_enum_values
    assert not missing, f"served OpenAPI is missing F5 RecommendedActionKind values: {missing}"


def test_served_schema_includes_active_exception_reason_kind(served_schema: dict) -> None:
    all_enum_values: set[str] = set()
    _collect_enum_values(served_schema.get("components", {}), all_enum_values)
    assert "active_exception" in all_enum_values


def test_change_approver_has_f5_approval_permissions_only() -> None:
    """T081 — change_approver carries uplift approval read/approve, not draft/manage."""
    perms = role_permissions(Role.change_approver)
    assert Permission.READ_UPLIFT in perms
    assert Permission.APPROVE_UPLIFT_WAVE in perms
    assert Permission.APPROVE_EXCEPTION in perms
    assert Permission.DRAFT_UPLIFT_WAVE not in perms
    assert Permission.MANAGE_EXCEPTION not in perms
