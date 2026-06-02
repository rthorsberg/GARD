"""Contract tests: AlignmentFindingKind enum matches finding-kinds.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from gard.models._enums import AlignmentFindingKind


def test_finding_kinds_match_contract(project_root: Path) -> None:
    contract_path = project_root / "specs/012-netbox-ipam-dcim-align/contracts/finding-kinds.yaml"
    raw = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    contract_kinds = set((raw.get("kinds") or {}).keys())
    app_kinds = {m.value for m in AlignmentFindingKind}
    assert app_kinds == contract_kinds
