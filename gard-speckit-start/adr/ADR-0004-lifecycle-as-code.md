# ADR-0004: Lifecycle-as-Code

## Status

Proposed

## Context

Firmware targets, prerequisites, upgrade paths, policies and command templates are critical lifecycle knowledge. If only stored manually in a UI/database, reviewability and change control may be weak.

## Decision

GARD shall support lifecycle catalogues as code.

Examples:

```text
gard-catalog/
├── vendors/
│   └── cisco/
│       └── isr1121/
│           ├── target.yaml
│           ├── upgrade-paths.yaml
│           ├── prerequisites.yaml
│           └── commands.yaml
├── policies/
└── normalization/
```

## Consequences

Positive:

- peer review
- pull requests
- diff and rollback
- better AI-agent compatibility
- stronger auditability

Negative:

- requires import/sync/validation pipeline
- may be less friendly than UI-only management for some users
