"""F6 — MVP vertical slice validation (Cisco ISR1121).

Maps 1:1 to specs/006-mvp-vertical-slice-cisco-isr1121/contracts/acceptance-matrix.yaml.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from gard.mcp.tools import count_devices_outside_target as count_tool
from gard.mcp.tools import create_uplift_wave_draft as wave_draft_tool
from gard.mcp.tools import get_ready_for_uplift_devices as ready_tool
from gard.models import AuditEvent, Device, LifecycleEvidence
from gard.models._enums import EvidenceType, LifecycleState
from tests.integration._mvp_isr1121_helpers import (
    BLOCKED_HOSTNAME,
    GOLDEN_HOSTNAME,
    PLATFORM_FAMILY,
    TARGET_VERSION,
    assert_isr1121_target_loaded,
    bootstrap_mvp_estate,
    device_by_hostname,
    evidence_for_import,
    import_isr1121_fixture,
    load_isr1121_catalogs,
    rest_outside_target_count,
    run_evaluations,
)
from tests.integration._uplift_helpers import future_window

pytestmark = pytest.mark.integration


class TestImport:
    def test_mixed_csv_import(self, client, db_session, project_root) -> None:
        """MVP-01 — valid and invalid rows import together."""
        headers, summary = import_isr1121_fixture(client, db_session, project_root)
        totals = summary["totals"]
        assert totals["rows_total"] == 5
        assert totals["rows_accepted"] == 2
        assert totals["rows_rejected"] == 1
        assert totals["rows_duplicate"] == 1
        assert totals["rows_manual_review"] == 1

        listed = client.get(
            "/api/v1/devices",
            params={"vendor_normalized": "cisco", "model_normalized": "ISR1121"},
            headers=headers,
        )
        assert listed.status_code == 200
        assert listed.json()["total_returned"] >= 2

    def test_import_summary_invariant(self, client, db_session, project_root) -> None:
        """MVP-02 — counter invariant holds."""
        _, summary = import_isr1121_fixture(client, db_session, project_root)
        t = summary["totals"]
        assert (
            t["rows_total"]
            == t["rows_accepted"]
            + t["rows_rejected"]
            + t["rows_duplicate"]
            + t["rows_manual_review"]
        )


class TestNormalize:
    def test_isr1121_normalization(self, client, db_session, project_root) -> None:
        """MVP-03 — canonical vendor/model/platform."""
        headers, _ = import_isr1121_fixture(client, db_session, project_root)
        golden = device_by_hostname(db_session, GOLDEN_HOSTNAME)
        assert golden.vendor_normalized == "cisco"
        assert golden.model_normalized == "ISR1121"
        assert golden.platform_family == "ios"

        listed = client.get(
            f"/api/v1/devices/{golden.id}",
            headers=headers,
        )
        assert listed.status_code == 200
        facts = listed.json()["facts"]
        assert facts["vendor_normalized"] == "cisco"
        assert facts["model_normalized"] == "ISR1121"


class TestCatalog:
    def test_isr1121_target_loaded(self, client, db_session, project_root) -> None:
        """MVP-04 — firmware target for reference model."""
        load_isr1121_catalogs(db_session, project_root)
        db_session.commit()
        target = assert_isr1121_target_loaded(db_session)
        assert target.platform_family == PLATFORM_FAMILY


class TestEvaluation:
    def test_isr1121_state_taxonomy(self, client, db_session, project_root) -> None:
        """MVP-05 — outside_target, blocked, and ready_for_uplift present."""
        headers, _ = import_isr1121_fixture(client, db_session, project_root)
        run_evaluations(client, headers)
        db_session.expire_all()

        golden = device_by_hostname(db_session, GOLDEN_HOSTNAME)
        blocked = device_by_hostname(db_session, BLOCKED_HOSTNAME)
        assert golden.lifecycle_state == LifecycleState.ready_for_uplift
        assert blocked.lifecycle_state == LifecycleState.blocked

        summary = client.get("/api/v1/readiness/summary", headers=headers)
        assert summary.status_code == 200
        body = summary.json()
        assert body["ready_for_uplift_count"] >= 1
        assert body["blocked_count"] >= 1

        comp = client.get("/api/v1/compliance/summary", headers=headers)
        assert comp.status_code == 200
        assert comp.json()["total_evaluated"] >= 2


class TestUplift:
    def test_create_plan(self, client, db_session, project_root) -> None:
        """MVP-06 — dry-run uplift plan."""
        ctx = bootstrap_mvp_estate(client, db_session, project_root, with_uplift=False)
        resp = client.post(
            "/api/v1/uplift/plans",
            json={"name": "mvp-plan-only", "description": "F6 plan test"},
            headers=ctx.drafter_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["id"]

    def test_draft_submit_approve_golden_path(self, client, db_session, project_root) -> None:
        """MVP-07 — wave draft through approved; golden lifecycle."""
        ctx = bootstrap_mvp_estate(client, db_session, project_root, with_uplift=True)
        assert ctx.wave_id is not None

        golden = db_session.get(Device, ctx.golden_device_id)
        assert golden is not None
        assert golden.lifecycle_state == LifecycleState.approved

        wave = client.get(f"/api/v1/uplift/waves/{ctx.wave_id}", headers=ctx.drafter_headers)
        assert wave.status_code == 200
        assert wave.json()["state"] == "approved"
        assert wave.json()["device_count"] >= 1


class TestMcpDelegates:
    """In-process delegates (F1-F7). Live Streamable HTTP transport: see ``tests/integration/test_mcp_transport_isr1121.py`` (F8 / MVP criterion #8)."""

    def test_count_outside_target_isr1121(self, client, db_session, project_root) -> None:
        """MVP-08 — MCP count matches REST outside_target devices."""
        bootstrap_mvp_estate(client, db_session, project_root, with_uplift=False)
        rest_count = rest_outside_target_count(db_session)

        mcp_out = count_tool.invoke(
            session=db_session,
            body=count_tool.CountDevicesOutsideTargetInput(
                vendor_normalized="cisco",
                platform_family=PLATFORM_FAMILY,
            ),
        )
        assert mcp_out.count == rest_count
        assert mcp_out.count >= 2

    def test_get_ready_for_uplift_isr1121(self, client, db_session, project_root) -> None:
        bootstrap_mvp_estate(client, db_session, project_root, with_uplift=False)
        out = ready_tool.invoke(
            session=db_session,
            body=ready_tool.GetReadyForUpliftDevicesInput(
                site="Oslo",
                vendor_normalized="cisco",
                platform_family=PLATFORM_FAMILY,
            ),
        )
        hostnames = {item.hostname for item in out.items}
        assert GOLDEN_HOSTNAME in hostnames
        assert BLOCKED_HOSTNAME not in hostnames

    def test_create_uplift_wave_draft_read_shaped(self, client, db_session, project_root) -> None:
        ctx = bootstrap_mvp_estate(client, db_session, project_root, with_uplift=False)
        plan = client.post(
            "/api/v1/uplift/plans",
            json={"name": "mcp-draft-plan", "description": "delegate test"},
            headers=ctx.drafter_headers,
        )
        plan_id = uuid.UUID(plan.json()["id"])
        start, end = future_window()
        draft = wave_draft_tool.invoke(
            session=db_session,
            body=wave_draft_tool.CreateUpliftWaveDraftInput(
                plan_id=plan_id,
                name="mcp-proposed-wave",
                target_version=TARGET_VERSION,
                target_platform_family=PLATFORM_FAMILY,
                scope_selector={"site_in": ["Oslo"], "platform_family": PLATFORM_FAMILY},
                change_window_start=start,
                change_window_end=end,
                mode="skip_ineligible",
            ),
        )
        assert draft.proposed_devices >= 1
        assert draft.target_version_live is True
        assert any(d.hostname == GOLDEN_HOSTNAME for d in draft.devices)


class TestAudit:
    def test_golden_device_audit_chain(self, client, db_session, project_root) -> None:
        """MVP-09 — audit spans import through approval."""
        ctx = bootstrap_mvp_estate(client, db_session, project_root, with_uplift=True)
        actions = {
            row.action
            for row in db_session.scalars(select(AuditEvent).order_by(AuditEvent.timestamp)).all()
        }
        assert any("import" in a for a in actions)
        assert "compliance.evaluation_triggered" in actions or "compliance.evaluated" in actions
        assert "readiness.evaluation_triggered" in actions or "readiness.evaluated" in actions
        assert "uplift_wave.drafted" in actions
        assert "uplift_wave.approved" in actions

        wave_audit = db_session.scalars(
            select(AuditEvent).where(AuditEvent.object_id == ctx.wave_id)
        ).all()
        assert wave_audit, "wave should have audit rows"
        approved = next(a for a in wave_audit if a.action == "uplift_wave.approved")
        assert approved.actor != "user:mvp-drafter"

    def test_lifecycle_evidence_emitted(self, client, db_session, project_root) -> None:
        """MVP-10 — import evidence + evaluation/planning audit trail."""
        ctx = bootstrap_mvp_estate(client, db_session, project_root, with_uplift=True)
        import_ev = evidence_for_import(db_session, ctx.import_job_id)
        assert len(import_ev) == 1
        assert import_ev[0].evidence_type == EvidenceType.import_event

        # Evaluation/planning: readiness + compliance persist as audit rows;
        # import is the primary LifecycleEvidence anchor for the slice.
        eval_audit = db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action.in_(
                    [
                        "compliance.evaluated",
                        "readiness.evaluated",
                        "uplift_wave.submitted",
                    ]
                )
            )
        ).all()
        assert eval_audit

        # Defensive: no unexpected empty evidence table after uplift path.
        any_evidence = db_session.scalars(select(LifecycleEvidence).limit(5)).all()
        assert any_evidence
