"""Contract test for F4 REST OpenAPI schema.

Loads the design-time contract
(``specs/004-readiness-prerequisites/contracts/rest-openapi.yaml``)
and asserts the four declared paths + methods are present in the
service's served ``/openapi.json``. Catches drift between the spec
and the FastAPI routes — mirrors the F3 contract test pattern.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from gard.api.app import create_app

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "004-readiness-prerequisites"
    / "contracts"
    / "rest-openapi.yaml"
)


def _load_contract_paths() -> dict[str, dict]:
    with CONTRACT.open() as fp:
        doc = yaml.safe_load(fp)
    return doc.get("paths", {})


@pytest.fixture(scope="module")
def served_schema() -> dict:
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/openapi.json")
        assert r.status_code == 200
        return r.json()


def test_contract_yaml_loads() -> None:
    assert CONTRACT.exists()
    paths = _load_contract_paths()
    assert len(paths) == 4, f"F4 declares 4 REST paths, got {len(paths)}"


def test_every_contract_path_is_served(served_schema: dict) -> None:
    served_paths = set(served_schema.get("paths", {}).keys())
    contract_paths = set(_load_contract_paths().keys())
    missing = contract_paths - served_paths
    assert not missing, f"contract paths missing from /openapi.json: {sorted(missing)}"


def test_every_contract_method_is_served(served_schema: dict) -> None:
    served_paths = served_schema.get("paths", {})
    for path, item in _load_contract_paths().items():
        served_methods = set(served_paths.get(path, {}).keys())
        contract_methods = {m for m in item if m in {"get", "post", "put", "patch", "delete"}}
        missing = contract_methods - served_methods
        assert not missing, (
            f"contract path {path} declares {contract_methods} but served exposes "
            f"{served_methods}; missing {missing}"
        )


def test_path_parameter_names_match(served_schema: dict) -> None:
    served_paths = served_schema.get("paths", {})
    for path, item in _load_contract_paths().items():
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
    """Recursively walk an OpenAPI JSON node and collect every `enum` list.

    Pydantic emits Literal types as inline `enum` keys, sometimes nested
    in `anyOf` / `oneOf` / `properties`. Scanning top-level
    `components.schemas` only misses inline enums.
    """
    if isinstance(node, dict):
        if "enum" in node and isinstance(node["enum"], list):
            acc.update(v for v in node["enum"] if isinstance(v, str))
        for v in node.values():
            _collect_enum_values(v, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_enum_values(item, acc)


def test_served_schema_includes_f4_recommended_action_kinds(served_schema: dict) -> None:
    """F4's REST schema MUST include the 5 new RecommendedActionKind values
    so AI agents + UI can parse the action payloads. Scans recursively
    because Pydantic emits Literal types inline rather than as named
    enums in components.schemas."""
    expected_kinds = {
        "schedule_uplift_wave",
        "hardware_refresh",
        "license_acquire",
        "firmware_intermediate_step",
        "import_observation",
    }
    all_enum_values: set[str] = set()
    _collect_enum_values(served_schema.get("components", {}), all_enum_values)
    missing = expected_kinds - all_enum_values
    assert not missing, (
        f"served OpenAPI is missing F4 RecommendedActionKind values: {missing}"
    )


def test_served_schema_includes_all_blocker_predicate_kinds(served_schema: dict) -> None:
    """The 11 BlockerPredicateKind values from data-model.md §2.2 MUST
    all appear in the served schema; locks against future enum drift."""
    expected = {
        "min_ram_mb",
        "min_disk_mb",
        "min_current_version",
        "hardware_revision_in",
        "license_present",
        "intermediate_version_required",
        "not_in_state",
        "region_in",
        "tagged_with",
        "missing_upgrade_path",
        "missing_observation_field",
    }
    all_enum_values: set[str] = set()
    _collect_enum_values(served_schema.get("components", {}), all_enum_values)
    missing = expected - all_enum_values
    assert not missing, f"served OpenAPI is missing BlockerPredicateKind values: {missing}"
