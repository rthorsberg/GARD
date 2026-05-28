# ADR-0010 — Normalization rules: YAML catalog with DB override layer, three-tier resolution

- **Status**: Accepted
- **Date**: 2026-05-27
- **Feature**: F1 (`001-device-import-normalize`)
- **Source decision**: research.md D5
- **Constitution principle**: III (Lifecycle-as-Code), IV (Audit & Explainability)

## Context

Operators want both:

1. **Code-reviewed, reproducible rules** — policy belongs in Git.
2. **A hot-fix path** — a brand-new device firmware string must be
   addable in minutes during a midnight migration, without a deploy.

A single mechanism can't satisfy both; we need a layered design with a
deterministic precedence order.

## Decision

### Storage layers (highest precedence first)

1. **Manual mapping** — `manual_mappings` table — an explicit, audited
   mapping for a specific `DeviceObservation.id`. Always wins; it is
   the codified human override and produces a `LifecycleEvidence` of
   `evidence_type="manual_mapping"`.
2. **DB override rule** — `normalization_rules` table — hot edits made
   through the API, ordered by `priority DESC, specificity DESC,
   created_at DESC`.
3. **File rule** — YAML files in `gard-catalog/normalization/*.yaml`,
   ordered by `priority DESC, specificity DESC, path-lexical ASC`.

Within a tier, **first match wins**. Tiers are evaluated top-down.

### Schema authority

The single source of truth for rule shape is
`gard-catalog/schemas/normalization-rule.schema.yaml`. Both YAML files
and DB `rule` JSONB columns are validated against it on load /
insert. CI runs this validation on every PR.

### Conflict policy

Two rules tied on `(tier, priority, specificity)` produce a
`RuleConflict` warning surfaced in the conflict report; resolution
falls back to `created_at DESC` (DB) or path-lexical (files). The
outcome is deterministic but flagged.

### Specificity

Number of constrained match fields, weighted toward exact > regex.
Computed once at load time and stored alongside the rule.

## Consequences

- Three-tier ordering is code-reviewable but operationally honest. The
  explainable response envelope returns
  `reasons[].kind="rule_match"` with `tier`, `id`, and `specificity`.
- The catalog ships with the container image; bumping rules ships as a
  new image OR as a DB row (operator's choice).
- DB overrides older than 30 days are flagged in a nightly report so
  they get graduated into the YAML catalog.
- We reject arbitrary code (Lua/Python) inside rules — they are pure
  declarative match → output mappings.

## Alternatives considered

- **YAML-only** — no hot-fix path.
- **DB-only** — violates Lifecycle-as-Code.
- **Rego/OPA** — powerful but premature; reconsider for F4's
  prerequisite engine.

## References

- research.md §D5
- contracts/normalization-rule.schema.yaml
- data-model.md §`normalization_rules`, §`manual_mappings`
- ROADMAP.md (ADR-0010 reservation)
