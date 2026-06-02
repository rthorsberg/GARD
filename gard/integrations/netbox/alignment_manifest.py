"""Load and validate the F12 NetBox alignment policy manifest."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from gard.core.logging import get_logger
from gard.models._enums import AlignmentFindingKind

_log = get_logger(__name__)

DEFAULT_MANIFEST_REL = Path("gard-catalog/netbox/alignment-policy-manifest.yaml")
SCHEMA_REL = Path(
    "specs/012-netbox-ipam-dcim-align/contracts/alignment-policy-manifest.schema.yaml"
)


class AlignmentManifestError(Exception):
    """Manifest load or semantic validation failed."""


@dataclass(frozen=True)
class MgmtIpPolicy:
    interface_name_patterns: tuple[str, ...]
    prefer_ipv4: bool
    require_assignment: bool


@dataclass(frozen=True)
class InterfacePolicy:
    id: str
    site: str
    role: str
    interface_pattern: str
    require_ip: bool
    allowed_modes: tuple[str, ...]


@dataclass(frozen=True)
class VrfExpectation:
    id: str
    site: str
    role: str
    interface_pattern: str
    expected_vrf: str


@dataclass(frozen=True)
class VlanExpectation:
    id: str
    site: str
    vlan_group_slug: str
    access_interface_pattern: str | None


@dataclass(frozen=True)
class OverlayExpectation:
    id: str
    service_slug: str
    site: str | None
    role: str | None
    import_rts: tuple[str, ...]
    export_rts: tuple[str, ...]


@dataclass(frozen=True)
class AlignmentPolicyManifest:
    schema_version: str
    sites: frozenset[str]
    roles: frozenset[str]
    vlan_groups: frozenset[tuple[str, str]]
    vrfs: frozenset[str]
    mgmt_ip: MgmtIpPolicy
    interface_policies: tuple[InterfacePolicy, ...]
    vrf_expectations: tuple[VrfExpectation, ...]
    vlan_expectations: tuple[VlanExpectation, ...]
    overlay_expectations: tuple[OverlayExpectation, ...]
    severity_overrides: dict[str, str]
    manifest_path: Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    return root / DEFAULT_MANIFEST_REL


def _load_schema(repo_root: Path) -> dict[str, Any]:
    schema_path = repo_root / SCHEMA_REL
    if not schema_path.is_file():
        raise AlignmentManifestError(f"manifest schema not found: {schema_path}")
    with schema_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise AlignmentManifestError("manifest schema is not a mapping")
    return data


def _compile_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    out: list[re.Pattern[str]] = []
    for pat in patterns:
        try:
            out.append(re.compile(pat))
        except re.error as exc:
            raise AlignmentManifestError(f"invalid regex {pat!r}: {exc}") from exc
    return tuple(out)


def _lint_manifest(manifest: AlignmentPolicyManifest) -> None:
    seen_policy_ids: set[str] = set()
    for policy in manifest.interface_policies:
        if policy.id in seen_policy_ids:
            raise AlignmentManifestError(f"duplicate interface policy id: {policy.id!r}")
        seen_policy_ids.add(policy.id)
        if policy.site != "*" and policy.site not in manifest.sites:
            raise AlignmentManifestError(
                f"interface policy {policy.id!r}: unknown site {policy.site!r}"
            )
        if policy.role != "*" and policy.role not in manifest.roles:
            raise AlignmentManifestError(
                f"interface policy {policy.id!r}: unknown role {policy.role!r}"
            )

    for vrf_exp in manifest.vrf_expectations:
        if vrf_exp.site not in manifest.sites:
            raise AlignmentManifestError(
                f"vrf expectation {vrf_exp.id!r}: unknown site {vrf_exp.site!r}"
            )
        if vrf_exp.role != "*" and vrf_exp.role not in manifest.roles:
            raise AlignmentManifestError(
                f"vrf expectation {vrf_exp.id!r}: unknown role {vrf_exp.role!r}"
            )
        if vrf_exp.expected_vrf not in manifest.vrfs:
            raise AlignmentManifestError(
                f"vrf expectation {vrf_exp.id!r}: unknown vrf {vrf_exp.expected_vrf!r}"
            )

    for vlan_exp in manifest.vlan_expectations:
        if vlan_exp.site not in manifest.sites:
            raise AlignmentManifestError(
                f"vlan expectation {vlan_exp.id!r}: unknown site {vlan_exp.site!r}"
            )
        key = (vlan_exp.site, vlan_exp.vlan_group_slug)
        if key not in manifest.vlan_groups:
            raise AlignmentManifestError(
                f"vlan expectation {vlan_exp.id!r}: vlan group {vlan_exp.vlan_group_slug!r} "
                f"not in catalogue for site {vlan_exp.site!r}"
            )

    for kind in manifest.severity_overrides:
        if kind not in {m.value for m in AlignmentFindingKind}:
            raise AlignmentManifestError(f"severity override for unknown kind: {kind!r}")


def load_alignment_manifest(
    *,
    manifest_path: Path | None = None,
    repo_root: Path | None = None,
) -> AlignmentPolicyManifest:
    """Load manifest YAML, validate schema, and lint semantic rules."""
    root = repo_root or _repo_root()
    mpath = manifest_path or default_manifest_path(root)

    if not mpath.is_file():
        raise AlignmentManifestError(f"manifest not found: {mpath}")

    with mpath.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise AlignmentManifestError("manifest root must be a mapping")

    schema = _load_schema(root)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        msg = "; ".join(f"{'/'.join(str(p) for p in err.path)}: {err.message}" for err in errors)
        raise AlignmentManifestError(f"manifest schema validation failed: {msg}")

    sites = frozenset(str(s) for s in (raw.get("sites") or []))
    roles = frozenset(str(r) for r in (raw.get("roles") or []))
    vlan_groups = frozenset(
        (str(vg["site"]), str(vg["group_slug"]))
        for vg in (raw.get("vlan_groups") or [])
        if isinstance(vg, dict)
    )
    vrfs = frozenset(str(v["name"]) for v in (raw.get("vrfs") or []) if isinstance(v, dict))

    mgmt_raw = raw["mgmt_ip"]
    mgmt_ip = MgmtIpPolicy(
        interface_name_patterns=tuple(str(p) for p in mgmt_raw["interface_name_patterns"]),
        prefer_ipv4=bool(mgmt_raw.get("prefer_ipv4", True)),
        require_assignment=bool(mgmt_raw.get("require_assignment", False)),
    )
    _compile_patterns(mgmt_ip.interface_name_patterns)

    interface_policies = tuple(
        InterfacePolicy(
            id=str(p["id"]),
            site=str(p["site"]),
            role=str(p["role"]),
            interface_pattern=str(p["interface_pattern"]),
            require_ip=bool(p["require_ip"]),
            allowed_modes=tuple(str(m) for m in (p.get("allowed_modes") or [])),
        )
        for p in (raw.get("interface_policies") or [])
        if isinstance(p, dict)
    )

    vrf_expectations = tuple(
        VrfExpectation(
            id=str(v["id"]),
            site=str(v["site"]),
            role=str(v.get("role", "*")),
            interface_pattern=str(v["interface_pattern"]),
            expected_vrf=str(v["expected_vrf"]),
        )
        for v in (raw.get("vrf_expectations") or [])
        if isinstance(v, dict)
    )

    vlan_expectations = tuple(
        VlanExpectation(
            id=str(v["id"]),
            site=str(v["site"]),
            vlan_group_slug=str(v["vlan_group_slug"]),
            access_interface_pattern=(
                str(v["access_interface_pattern"]) if v.get("access_interface_pattern") else None
            ),
        )
        for v in (raw.get("vlan_expectations") or [])
        if isinstance(v, dict)
    )

    overlay_expectations = tuple(
        OverlayExpectation(
            id=str(o["id"]),
            service_slug=str(o["service_slug"]),
            site=str(o["site"]) if o.get("site") else None,
            role=str(o["role"]) if o.get("role") else None,
            import_rts=tuple(str(rt) for rt in (o.get("import_rts") or [])),
            export_rts=tuple(str(rt) for rt in (o.get("export_rts") or [])),
        )
        for o in (raw.get("overlay_expectations") or [])
        if isinstance(o, dict)
    )

    severity_overrides = {str(k): str(v) for k, v in (raw.get("severity_overrides") or {}).items()}

    manifest = AlignmentPolicyManifest(
        schema_version=str(raw["schema_version"]),
        sites=sites,
        roles=roles,
        vlan_groups=vlan_groups,
        vrfs=vrfs,
        mgmt_ip=mgmt_ip,
        interface_policies=interface_policies,
        vrf_expectations=vrf_expectations,
        vlan_expectations=vlan_expectations,
        overlay_expectations=overlay_expectations,
        severity_overrides=severity_overrides,
        manifest_path=mpath,
    )
    _lint_manifest(manifest)
    _log.info(
        "alignment_manifest.loaded",
        path=str(mpath),
        policies=len(interface_policies),
    )
    return manifest
