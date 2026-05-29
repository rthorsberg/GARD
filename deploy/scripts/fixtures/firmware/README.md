# Firmware catalog fixtures

The seed/reset path for the firmware catalog does **not** maintain a separate
copy of YAML fixtures under `deploy/scripts/fixtures/firmware/` — the
in-repo `gard-catalog/firmware/` tree IS the seed. `seed.sh` mounts it
into the container and triggers a `gard catalog reload firmware` against
it.

Why this differs from `deploy/scripts/fixtures/devices.csv`:

- **Device CSVs** are POSTed to `/api/v1/imports/devices/csv` over HTTP, so
  they have to live somewhere the host shell can stream from. A separate
  fixture file under `deploy/scripts/fixtures/` is the natural answer.
- **Catalog YAMLs** are read by the loader from disk, not POSTed. The
  loader's `root_path` resolves to `gard-catalog/firmware/` — which is
  already the source of truth in the repo. Duplicating the files would
  invite drift and serve no purpose.

If you need a sandbox catalog for adversarial-input tests, put it under
`tests/fixtures/firmware/` (used by the contract + integration tests) —
the loader takes a `root_path` argument so tests can point at any
directory.
