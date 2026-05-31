# ADR-0018 — NetBox Ecosystem Positioning (Diode, Discovery, Assurance)

**Status**: Accepted
**Date**: 2026-05-31
**Decision-makers**: GARD core team
**Touches**: F7 (NetBox Integration — read-only), roadmap (Assurance complement, Diode deferral)
**Supersedes**: none
**Superseded by**: none

## Context

Modern NetBox deployments rarely treat NetBox as a manually curated island. Typical data flow:

```
Network / cloud sources → NetBox Discovery → NetBox Diode → NetBox (SoT)
                                                              ↓
                                                    downstream consumers
```

**NetBox Diode** is a write-into-NetBox ingestion path (gRPC/SDK). It is how discovery pipelines populate NetBox — not how downstream tools should bypass NetBox.

**NetBox Assurance** (NetBox Labs) monitors inventory and configuration drift against NetBox-as-source-of-truth. It answers "does reality match what NetBox says?"

GARD answers a different question: "does firmware lifecycle state match policy intent, and is the device ready for uplift?"

F7 must document where GARD sits in this ecosystem so operators do not confuse GARD with a Diode client or an Assurance replacement.

## Decision

### A. GARD is a downstream NetBox consumer, not a Diode client

F7 integrates exclusively via **NetBox REST API** against an already-populated NetBox instance.

- GARD does **not** implement Diode gRPC ingest in v1.
- GARD does **not** replace NetBox Discovery or Diode as an ingestion path.
- Operators who use Diode to feed NetBox continue that pattern unchanged; GARD reads the result.

A post-v1 **Diode-SDK adapter** (for sites where Diode is the only permitted data plane) is a roadmap follow-up, not F7 scope.

### B. Complementary positioning vs NetBox Assurance

| Concern | NetBox Assurance | GARD |
|---|---|---|
| Inventory/config drift vs NetBox | Primary | Out of scope v1 |
| Firmware version drift vs policy | Secondary / plugin territory | **Primary** |
| Readiness prerequisites | Not core | **Primary** (F2–F4) |
| Uplift planning & approval | Not core | **Primary** (F5) |
| Execution evidence | Partial | **Primary** (audit chain) |

GARD and Assurance are **complementary** on the same NetBox source-of-truth. An operator may run both: Assurance for config/inventory drift, GARD for firmware lifecycle governance.

F7 does not integrate with Assurance APIs in v1.

### C. Dev stack isolation (R-1, R-2, R-6)

GARD ships an **optional** isolated dev NetBox stack:

- Compose project: `gard-f7-netbox`
- Host ports: UI **18888**, Postgres **55432**
- Never publishes 5432, 8080, or 18080 (avoids GARD app and existing lab stacks)

Operators **may** point GARD at an existing NetBox instance (e.g. `http://127.0.0.1:18080`) instead of starting the dev stack. Docker isolation is for greenfield labs, not a requirement.

Destructive Docker commands (`docker system prune`, `compose down -v` without `-p gard-f7-netbox`) are forbidden in GARD documentation — existing operator NetBox containers must not be touched.

### D. Observed firmware stays on GARD paths

NetBox device records may carry software version custom fields in some deployments. F7 v1 **does not** map NetBox firmware fields into GARD observed state.

Rationale: observed firmware in GARD flows through normalization rules and adapter paths (F1/F3). Mixing NetBox-reported versions without a defined normalization contract would create a second, inconsistent observation source.

## Rationale

**Why REST-only**: NetBox REST is the stable, operator-familiar contract. Diode is an ingestion protocol for writers, not readers. GARD's read-only role aligns with REST consumption of NetBox-as-SoT.

**Why explicit Assurance complement**: Without this ADR, stakeholders will ask "why not just use Assurance?" The answer is scope separation — Assurance does not own uplift approval chains or firmware catalog policy.

**Why optional dev stack with high ports**: User constraint — multiple NetBox Docker instances already exist. Isolation by project name + non-colliding ports prevents accidental teardown or port binding failures.

## Alternatives considered

1. **GARD as Diode consumer**. Rejected — Diode is write-oriented; GARD v1 is read-only downstream of NetBox.
2. **GARD replaces Assurance for firmware**. Rejected — Assurance may add firmware checks; GARD does not claim to replace Assurance inventory/config monitoring.
3. **Map NetBox custom fields for firmware in v1**. Rejected — requires per-deployment field mapping and normalization rules not yet specified.
4. **Embed NetBox in GARD compose**. Rejected (R-1) — couples lifecycles and increases teardown risk.

## Consequences

- F7 documentation (`deploy/netbox/README.md`, quickstart) MUST include Docker safety rules and existing-instance override.
- Roadmap positions F7 as ecosystem-aware read integration, not a NetBox fork.
- Future Diode adapter or Assurance integration each require their own ADR and feature slice.
- Marketing and operator docs use the phrase "downstream consumer of NetBox-as-source-of-truth."
