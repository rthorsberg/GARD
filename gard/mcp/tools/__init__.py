"""F3 compliance MCP tool delegates.

Per ADR-0013 the MCP transport is deferred to a follow-up feature
(F008). Each module here exposes a Pydantic input model + output model
+ a synchronous ``invoke`` function that returns the output model. The
transport feature will wire these modules to the MCP server with no
per-tool code change.

Tests in ``tests/contract/test_compliance_mcp_tools.py`` validate the
schema metadata (auth, input/output schemas) against the YAML contract.
``tests/integration/test_us3_mcp_parity.py`` asserts byte-parity with
the REST equivalents.
"""

from __future__ import annotations
