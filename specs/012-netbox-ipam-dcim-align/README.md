# F12 — NetBox IPAM & DCIM Alignment

**Branch**: `012-netbox-ipam-dcim-align`
**Status**: Tasks generated — ready for `/speckit-implement`

## Summary

Extend NetBox sync with post-reconcile IPAM/overlay alignment: pull interface/IP/VRF/VLAN/RT context, validate against policy manifest, persist findings, surface in API and operator portal.

## Artifacts

| File | Purpose |
|------|---------|
| [spec.md](./spec.md) | Feature specification |
| [plan.md](./plan.md) | Implementation plan |
| [research.md](./research.md) | Design decisions R-1..R-12 |
| [data-model.md](./data-model.md) | Postgres + manifest model |
| [quickstart.md](./quickstart.md) | Operator runbook |
| [tasks.md](./tasks.md) | 51 implementation tasks (T001–T051) |
| [contracts/](./contracts/) | Manifest schema, finding kinds, OpenAPI |

## Next

```bash
/speckit-implement
```
