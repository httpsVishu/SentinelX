"""LangGraph orchestration: the seven agents as three state machines.

1. scan graph: Recon -> Mapping -> Assessment -> Validation.
   Confirmed findings above Informational severity are stored as
   PENDING_ADMIN_REVIEW and the run ends. Human sign-off happens outside the
   graph, through the review API.
2. post-approval graph: Reporting -> Accountability. Run once per finding,
   after an Admin approves it.
3. verification graph: scoped Assessment -> Validation -> Verification. Run
   after a Vendor reports a fix.

Nodes only call agents and thread state. Writes to Finding and Ticket rows
happen in the run_* functions after a graph finishes.
"""
import uuid
from datetime import datetime, timezone

from langgraph.graph import END, StateGraph
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.accountability_agent import AccountabilityAgent
from app.agents.assessment_agent import AssessmentAgent
from app.agents.base_agent import AgentExecutionFailed
from app.agents.mapping_agent import MappingAgent
from app.agents.pipeline_state import (
    PostApprovalPipelineState,
    ScanPipelineState,
    VerificationPipelineState,
)
from app.agents.recon_agent import ReconAgent
from app.agents.reporting_agent import ReportingAgent
from app.agents.validation_agent import ValidationAgent
from app.agents.verification_agent import VerificationAgent
from app.core.crypto import decrypt_text, encrypt_text
from app.models.enums import (
    AlertTriggerType,
    FindingStatus,
    Severity,
    TicketStatus,
    UserRole,
    VerificationResult,
)
from app.models.finding import Finding
from app.models.site import Site
from app.models.ticket import Ticket
from app.models.user import User
from app.services import ticket_service
from app.services.alert_service import create_and_dispatch_alert

# A finding in one of these states, on the same site, title and endpoint, means
# a new scan has nothing new to report. Discarded and inconclusive results are
# not listed, so they can be recorded again.
_ALREADY_KNOWN_STATUSES = (
    FindingStatus.PENDING_ADMIN_REVIEW,
    FindingStatus.CONFIRMED,
    FindingStatus.APPROVED,
    FindingStatus.REJECTED,
    FindingStatus.NEEDS_MANUAL_REVIEW,
)

# ==============================================================================
# 1. Scan graph: Recon -> Mapping -> Assessment -> Validation
# ==============================================================================


def _build_scan_graph(db: Session):
    def recon_node(state: ScanPipelineState) -> ScanPipelineState:
        try:
            state.recon_output = ReconAgent(db).run(
                state.scan_id,
                {"target_url": state.target_url, "excluded_paths": state.excluded_paths},
            )
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    def mapping_node(state: ScanPipelineState) -> ScanPipelineState:
        if state.recon_output is None:
            return state  # upstream failure
        try:
            state.mapping_output = MappingAgent(db).run(state.scan_id, {"recon_output": state.recon_output})
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    def assessment_node(state: ScanPipelineState) -> ScanPipelineState:
        try:
            state.assessment_output = AssessmentAgent(db).run(
                state.scan_id,
                {
                    "target_url": state.target_url,
                    "excluded_paths": state.excluded_paths,
                    "scope_paths": state.scope_paths,
                },
            )
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    def validation_node(state: ScanPipelineState) -> ScanPipelineState:
        if state.assessment_output is None:
            return state
        try:
            state.validation_output = ValidationAgent(db).run(
                state.scan_id, {"raw_findings": state.assessment_output.get("raw_findings", [])}
            )
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    graph = StateGraph(ScanPipelineState)
    graph.add_node("recon", recon_node)
    graph.add_node("mapping", mapping_node)
    graph.add_node("assessment", assessment_node)
    graph.add_node("validation", validation_node)
    graph.set_entry_point("recon")
    graph.add_edge("recon", "mapping")
    graph.add_edge("mapping", "assessment")
    graph.add_edge("assessment", "validation")
    graph.add_edge("validation", END)
    return graph.compile()


def run_scan_pipeline(
    db: Session, scan_id: uuid.UUID, site: Site, scope_paths: list[str] | None = None
) -> ScanPipelineState:
    """Runs the scan graph, stores new findings, and alerts the admins about
    Critical and High findings that now wait for review."""
    initial_state = ScanPipelineState(
        scan_id=scan_id,
        site_id=site.id,
        target_url=site.url,
        excluded_paths=site.excluded_paths,
        scope_paths=scope_paths,
    )
    result = _build_scan_graph(db).invoke(initial_state)
    final_state = ScanPipelineState(**result) if isinstance(result, dict) else result

    created = _persist_findings_from_validation(db, scan_id, site, final_state)
    _alert_admins_of_new_findings(db, site, created)
    return final_state


def _already_known(db: Session, site_id: uuid.UUID, title: str, endpoint: str) -> bool:
    """True if this site already has this finding in a state that needs no new
    record. A finding whose ticket was verified closed does not count: if it
    comes back, that is a repeat vulnerability and gets a new finding."""
    stmt = (
        select(Finding.id)
        .outerjoin(Ticket, Ticket.finding_id == Finding.id)
        .where(
            Finding.site_id == site_id,
            Finding.title == title,
            Finding.affected_endpoint == endpoint,
            Finding.status.in_(_ALREADY_KNOWN_STATUSES),
            or_(Ticket.id.is_(None), Ticket.status != TicketStatus.VERIFIED_CLOSED),
        )
        .limit(1)
    )
    return db.execute(stmt).first() is not None


def _persist_findings_from_validation(
    db: Session, scan_id: uuid.UUID, site: Site, state: ScanPipelineState
) -> list[Finding]:
    if state.assessment_output is None or state.validation_output is None:
        return []

    raw_findings = state.assessment_output.get("raw_findings", [])
    created: list[Finding] = []

    for item in state.validation_output.get("validated_findings", []):
        index = item.get("raw_finding_index")
        if index is None or not (0 <= index < len(raw_findings)):
            continue
        raw = raw_findings[index]
        severity = Severity(item.get("severity", "informational"))

        # Only Confirmed findings above Informational go to Admin review
        # (SRS 4.5-2). Informational ones may proceed automatically.
        status_by_verdict = {
            "confirmed": (
                FindingStatus.PENDING_ADMIN_REVIEW if severity != Severity.INFORMATIONAL else FindingStatus.CONFIRMED
            ),
            "discarded": FindingStatus.DISCARDED,
            "inconclusive": FindingStatus.INCONCLUSIVE,
            "needs_manual_review": FindingStatus.NEEDS_MANUAL_REVIEW,
        }
        status = status_by_verdict.get(item.get("verdict"), FindingStatus.INCONCLUSIVE)

        if _already_known(db, site.id, raw["title"], raw["affected_endpoint"]):
            continue

        finding = Finding(
            site_id=site.id,
            scan_id=scan_id,
            title=raw["title"],
            description=raw["description"],
            severity=severity,
            confidence=item.get("confidence", 0.5),
            affected_endpoint=raw["affected_endpoint"],
            status=status,
            raw_scanner_output_encrypted=encrypt_text(db, str(raw.get("raw_output", {}))),
            poc_summary_encrypted=encrypt_text(db, item.get("poc_summary")),
            validated_at=datetime.now(timezone.utc),
        )
        db.add(finding)
        db.flush()  # so a duplicate later in this same scan is seen by _already_known
        created.append(finding)

    db.commit()
    return created


def _alert_admins_of_new_findings(db: Session, site: Site, findings: list[Finding]) -> None:
    """SRS 4.5-4 trigger (a): a new Critical or High finding was confirmed."""
    urgent = [
        f
        for f in findings
        if f.status == FindingStatus.PENDING_ADMIN_REVIEW and f.severity in (Severity.CRITICAL, Severity.HIGH)
    ]
    if not urgent:
        return

    admins = db.execute(
        select(User).where(User.department_id == site.department_id, User.role == UserRole.ADMIN)
    ).scalars().all()

    for finding in urgent:
        trigger = (
            AlertTriggerType.CRITICAL_FINDING_CONFIRMED
            if finding.severity == Severity.CRITICAL
            else AlertTriggerType.HIGH_FINDING_CONFIRMED
        )
        for admin in admins:
            create_and_dispatch_alert(
                db,
                admin,
                trigger,
                site_name=site.name,
                action_required="Review the finding in the review queue.",
                severity=finding.severity.value,
                site_id=site.id,
                finding_id=finding.id,
            )


# ==============================================================================
# 2. Post-approval graph: Reporting -> Accountability
# ==============================================================================


def run_post_approval_pipeline(
    db: Session, scan_id: uuid.UUID, finding: Finding, department_id: uuid.UUID
) -> PostApprovalPipelineState:
    """Reporting then Accountability for an approved finding, then stores the
    report on the finding and creates the ticket. scan_id is the originating
    scan, reused so these executions link back to it (no new scan is created)."""
    poc_summary = decrypt_text(db, finding.poc_summary_encrypted)

    def reporting_node(state: PostApprovalPipelineState) -> PostApprovalPipelineState:
        try:
            state.reporting_output = ReportingAgent(db).run(
                scan_id,
                {
                    "finding_id": str(finding.id),
                    "title": finding.title,
                    "severity": finding.severity.value,
                    "affected_endpoint": finding.affected_endpoint,
                    "poc_summary": poc_summary or "",
                },
            )
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    def accountability_node(state: PostApprovalPipelineState) -> PostApprovalPipelineState:
        try:
            state.accountability_output = AccountabilityAgent(db).run(
                scan_id,
                {
                    "finding_id": str(finding.id),
                    "site_id": str(finding.site_id),
                    "department_id": str(department_id),
                    "severity": finding.severity.value,
                },
            )
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    graph = StateGraph(PostApprovalPipelineState)
    graph.add_node("reporting", reporting_node)
    graph.add_node("accountability", accountability_node)
    graph.set_entry_point("reporting")
    graph.add_edge("reporting", "accountability")
    graph.add_edge("accountability", END)

    initial_state = PostApprovalPipelineState(
        finding_id=finding.id, site_id=finding.site_id, department_id=department_id
    )
    result = graph.compile().invoke(initial_state)
    final_state = PostApprovalPipelineState(**result) if isinstance(result, dict) else result

    if final_state.reporting_output:
        finding.plain_language_report = final_state.reporting_output.get("plain_language_report")
        finding.remediation_guidance = final_state.reporting_output.get("remediation_guidance")
        db.commit()
        db.refresh(finding)

    if final_state.accountability_output:
        ticket_service.create_ticket_from_approved_finding(db, finding, department_id)

    return final_state


# ==============================================================================
# 3. Verification graph: Assessment (scoped) -> Validation -> Verification
# ==============================================================================


def run_verification_pipeline(
    db: Session,
    scan_id: uuid.UUID,
    ticket_id: uuid.UUID,
    site: Site,
    affected_endpoint: str,
    original_title: str | None = None,
) -> VerificationPipelineState:
    """A narrow re-check of one endpoint, then the Verification Agent's
    decision. Only a passed or failed result is written to the ticket, through
    ticket_service.record_verification_result(). An inconclusive result leaves
    the ticket untouched for the caller to flag."""

    def assessment_node(state: VerificationPipelineState) -> VerificationPipelineState:
        try:
            state.assessment_output = AssessmentAgent(db).run(
                scan_id,
                {
                    "target_url": state.target_url,
                    "excluded_paths": state.excluded_paths,
                    "scope_paths": [state.affected_endpoint],
                },
            )
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    def validation_node(state: VerificationPipelineState) -> VerificationPipelineState:
        if state.assessment_output is None:
            return state
        try:
            state.validation_output = ValidationAgent(db).run(
                scan_id, {"raw_findings": state.assessment_output.get("raw_findings", [])}
            )
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    def verification_node(state: VerificationPipelineState) -> VerificationPipelineState:
        assessment = state.assessment_output or {}
        try:
            state.verification_output = VerificationAgent(db).run(
                scan_id,
                {
                    "ticket_id": str(state.ticket_id),
                    "affected_endpoint": state.affected_endpoint,
                    "original_title": state.original_title,
                    "validated_findings": (state.validation_output or {}).get("validated_findings", []),
                    "raw_titles": [f.get("title", "") for f in assessment.get("raw_findings", [])],
                    "tools_invoked": assessment.get("tools_invoked", []),
                    "tool_errors": assessment.get("tool_errors", []),
                },
            )
        except AgentExecutionFailed as exc:
            state.errors.append(str(exc))
        return state

    graph = StateGraph(VerificationPipelineState)
    graph.add_node("assessment", assessment_node)
    graph.add_node("validation", validation_node)
    graph.add_node("verification", verification_node)
    graph.set_entry_point("assessment")
    graph.add_edge("assessment", "validation")
    graph.add_edge("validation", "verification")
    graph.add_edge("verification", END)

    initial_state = VerificationPipelineState(
        scan_id=scan_id,
        ticket_id=ticket_id,
        site_id=site.id,
        target_url=site.url,
        excluded_paths=site.excluded_paths,
        affected_endpoint=affected_endpoint,
        original_title=original_title,
    )
    result = graph.compile().invoke(initial_state)
    final_state = VerificationPipelineState(**result) if isinstance(result, dict) else result

    output = final_state.verification_output
    if output and output.get("result") in ("passed", "failed"):
        ticket_service.record_verification_result(
            db, ticket_id, scan_id, VerificationResult(output["result"]), notes=output.get("notes")
        )

    return final_state