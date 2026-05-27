# Product Brief: GARD

## Name

**GARD**

Suggested expansion:

- **GARD** = Service Lifecycle Guardrails
- Nordic meaning: from *gard/garðr*, an enclosure, protection boundary, or guarded domain.

## Product category

Firmware/software lifecycle governance platform for CSP network infrastructure.

## One-liner

**GARD gives a CSP control over the firmware/software lifecycle of its network estate — from discovered actual state to approved target state, safe uplift planning, and lifecycle evidence.**

## Problem

CSPs often operate large, heterogeneous network estates with legacy infrastructure. Firmware/software lifecycle has historically been handled through spreadsheets, vendor documents, manual operational knowledge, ad hoc scripts, ACS platforms, and fragmented inventory views.

This creates:

- unknown firmware/software versions
- unsupported or vulnerable software
- unclear target versions per vendor/model
- missing prerequisite knowledge
- inconsistent upgrade paths
- weak readiness validation
- manual and undocumented uplift procedures
- poor auditability and evidence
- difficulty prioritizing risk-reducing upgrades

## Vision

GARD becomes the CSP's firmware lifecycle control plane.

It answers:

1. What software/firmware is each device currently running?
2. What should it be running?
3. What is the drift?
4. What is the risk?
5. Is it ready to be uplifted?
6. What exact plan would make it compliant?
7. Who approved it?
8. What evidence proves the final state?

## Core mental model

```text
Observe   -> collect/import actual state
Compare   -> compare against target state
Plan      -> calculate safe uplift plan
Approve   -> require governance gate
Apply     -> execute or guide execution through adapters
Verify    -> validate actual post-state
Evidence  -> record proof
Reconcile -> update lifecycle state
```

## Primary users

- Network lifecycle manager
- Network engineer
- Security/compliance responsible
- Operations manager
- Automation/orchestration systems
- AI agents/chatbots through MCP

## North star

> No device left unknown. No firmware left unmanaged. No uplift without readiness.
