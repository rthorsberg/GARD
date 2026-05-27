# Prompts for Speckit Continuation

## Constitution Prompt

Create a project constitution for GARD, an MCP-native firmware lifecycle governance platform for CSP network infrastructure. The constitution must enforce: governance before execution, desired vs actual state separation, risk/readiness separation, safe MCP tools, lifecycle-as-code, explicit approval gates, auditability, evidence, and clear source-of-truth boundaries with NetBox and execution adapters.

## Specification Prompt

Create a detailed product specification for GARD based on the included PRD and domain model. The spec must cover CSV ingestion, normalization, firmware target catalogue, package catalogue, upgrade path engine, prerequisite/rule engine, compliance/readiness evaluation, drift taxonomy, uplift planning, wave management, MCP tools, NetBox integration, TR-069 positioning, evidence, security, RBAC and audit.

## Plan Prompt

Create an implementation plan for a vertical-slice MVP of GARD. Prioritize the smallest useful implementation that supports one reference device family, CSV import, normalization, target mapping, compliance/readiness evaluation, dry-run plan generation, draft wave creation, audit logging, REST API and MCP query tools.

## Tasks Prompt

Generate implementation tasks suitable for an AI coding agent. Tasks should be dependency-ordered and grouped by backend domain model, database migrations, CSV import, rule engine, API, MCP server, examples, tests and documentation. Include acceptance criteria per task.

## ADR Prompt

Review the proposed ADRs and create additional ADRs for: database choice, API-first design, MCP security boundary, lifecycle evidence vs SEGL, CSV-first ingestion, adapter architecture, and manual-guided v1 execution.
