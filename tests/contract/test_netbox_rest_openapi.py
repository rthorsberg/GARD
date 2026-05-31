"""Contract test for F7 REST OpenAPI schema."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from gard.api.app import create_app

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "007-netbox-integration-read"
    / "contracts"
    / "rest-openapi.yaml"
)


def _load_contract_paths() -> dict[str, dict]:
    with CONTRACT.open() as fp:
        doc = yaml.safe_load(fp)
    paths = doc.get("paths", {})
    base = doc.get("servers", [{}])[0].get("url", "")
    if base and not base.endswith("/"):
        base = base + "/"
    return {f"{base.rstrip('/')}{path}": item for path, item in paths.items()}


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
    assert len(paths) == 4, f"F7 declares 4 REST paths, got {len(paths)}"


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
