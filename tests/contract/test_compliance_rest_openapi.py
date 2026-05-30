"""Contract test for F3 REST OpenAPI schema.

Loads the design-time contract
(``specs/003-compliance-drift-evaluation/contracts/rest-openapi.yaml``)
and asserts the four declared paths + methods are present in the
service's served ``/openapi.json``. Catches future drift between the
spec and the FastAPI routes.

We do **not** assert byte-equality of schema shapes — Pydantic emits
slightly different envelopes than hand-written YAML (default values,
`null` representations). The test compares:

- path existence
- method existence per path
- the operation's required parameter names (path + query) are a
  superset of those declared in the contract
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
    / "003-compliance-drift-evaluation"
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
    assert len(paths) == 4, f"F3 declares 4 REST paths, got {len(paths)}"


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
