# F6 — Data Model (fixture map)

F6 introduces **no new database tables**. This document maps the ISR1121 vertical-slice fixtures to existing entities so implementers know what to seed and assert.

## Fixture CSV → persisted entities

| CSV row role | Expected `Device` | Expected normalization | Expected compliance | Expected readiness |
|---|---|---|---|---|
| Golden ISR1121 (`r-osl-001`) | `lifecycle_state` progresses to `approved` | `vendor_normalized=Cisco`, `model_normalized=ISR1121`, `platform_family=ios` | Starts `outside_target`, target `17.12.4` | Ends `ready_for_uplift` before wave; `approval_pending` during review |
| Secondary ISR1121 (blocked) | Stays `blocked` or `outside_target` | Same family | `outside_target` or `package_drift` | `blocked` with visible blocker predicate |
| Malformed row | Not persisted | — | — | — |
| Duplicate row | `rows_duplicate` in import summary | — | — | — |
| Non-ISR1121 (optional) | Persisted but excluded from ISR1121-filtered queries | Other vendor | Varies | Varies |

## Catalog → desired state

| Catalog file | Entity | Golden device usage |
|---|---|---|
| `cisco-ios-isr1121.yaml` | `FirmwareTarget` | Defines `target_version=17.12.4` |
| `cisco-ios-16.9.5.yaml` | `FirmwarePackage` | Matches observed firmware on golden device |
| `cisco-ios-17.12.4.yaml` | `FirmwarePackage` | Wave `target_version` |
| `cisco-ios-isr1121.yaml` (upgrade path) | `UpgradePath` | Satisfies `missing_upgrade_path` blocker if evaluated |
| `isr1121-minimum-flash.yaml` | `PrerequisiteRule` | Observation fields must satisfy for `ready_for_uplift` |

## Planning artefacts (F5)

| Step | Entity | Golden device |
|---|---|---|
| Create plan | `UpliftPlan` | One plan per test run |
| Draft wave | `UpliftWave` + `UpliftWaveDevice` | Golden device in `devices[]`, `state=draft` |
| Submit | Wave `state=submitted`, device `approval_pending` | |
| Approve | Wave `state=approved`, device `approved`, citation stored | SoD: drafter ≠ approver |

## Audit / evidence expectations

Minimum `audit_events` action types for golden device (substring match acceptable):

| Phase | Expected actions |
|---|---|
| Import | device import / job completion |
| Compliance | compliance evaluation |
| Readiness | readiness evaluation |
| Uplift | `uplift_wave.drafted`, submit, approve |

`LifecycleEvidence` rows: assert presence where F1–F5 already emit them (import, catalog reload, evaluation) — exact `evidence_type` strings matched in test constants sourced from existing emit sites.

## MCP delegate inputs (no new schema)

| Delegate | Filter inputs | Expected output shape |
|---|---|---|
| `count_devices_outside_target` | vendor/model ISR1121 | Integer matching REST compliance count |
| `get_ready_for_uplift_devices` | site filter | List containing golden hostname |
| `create_uplift_wave_draft` | scope + target version | Read-shaped envelope, no DB write |
| `get_uplift_plan_summary` | plan id | Plan + wave counts after draft |
