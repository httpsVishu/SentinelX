"""Controlled enumerations shared across models, schemas, services and the
frontend (see docs/API.md for the frontend-side mirror of these values).

Native Python and Postgres enums enforce the SRS requirement that status
fields are restricted to a fixed set of values, not free text.
"""
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VENDOR = "vendor"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class FindingStatus(str, enum.Enum):
    RAW = "raw"                          # just produced by the Assessment Agent
    CONFIRMED = "confirmed"              # Validation Agent proved it real
    DISCARDED = "discarded"              # Validation Agent: false positive
    INCONCLUSIVE = "inconclusive"        # scanner or tool failure during validation
    NEEDS_MANUAL_REVIEW = "needs_manual_review"  # proof judged too risky to run
    PENDING_ADMIN_REVIEW = "pending_admin_review"  # confirmed, above Informational
    APPROVED = "approved"                # Admin approved, goes on to Reporting
    REJECTED = "rejected"                # Admin rejected, no ticket


class TicketStatus(str, enum.Enum):
    UNASSIGNED = "unassigned"                          # no vendor mapped to the site
    OPEN = "open"                                       # assigned, within deadline
    OVERDUE = "overdue"                                  # deadline passed, still open
    FIX_SUBMITTED_PENDING_VERIFICATION = "fix_submitted_pending_verification"
    VERIFIED_CLOSED = "verified_closed"                  # re-scan confirmed the fix
    FIX_FAILED_REOPENED = "fix_failed_reopened"          # re-scan found it still present


class DeadlineSource(str, enum.Enum):
    AUTO = "auto"          # calculated from severity via the SLA settings
    OVERRIDE = "override"  # an Admin changed the suggested deadline


class ScanTriggerType(str, enum.Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    VERIFICATION = "verification"


class ScanStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentName(str, enum.Enum):
    RECON = "recon"
    MAPPING = "mapping"
    ASSESSMENT = "assessment"
    VALIDATION = "validation"
    REPORTING = "reporting"
    ACCOUNTABILITY = "accountability"
    VERIFICATION = "verification"


class AgentExecutionStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReviewDecision(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"


class VerificationResult(str, enum.Enum):
    PASSED = "passed"   # vulnerability no longer present
    FAILED = "failed"   # vulnerability still present


class AlertTriggerType(str, enum.Enum):
    CRITICAL_FINDING_CONFIRMED = "critical_finding_confirmed"
    HIGH_FINDING_CONFIRMED = "high_finding_confirmed"
    UNAUTHORIZED_CHANGE = "unauthorized_change"
    DEADLINE_MISSED = "deadline_missed"
    VERIFICATION_FAILED = "verification_failed"
    SCAN_FAILED = "scan_failed"
    PIPELINE_FAILURE = "pipeline_failure"
    TICKET_ASSIGNED = "ticket_assigned"                  # sent to the vendor (SRS 4.3-4)
    TICKET_DEADLINE_CHANGED = "ticket_deadline_changed"  # sent to the vendor


class AlertLevel(str, enum.Enum):
    URGENT = "urgent"
    WARNING = "warning"
    INFO = "info"


class AlertDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    SUPPRESSED = "suppressed"  # recipient muted this kind of alert


class AuditAction(str, enum.Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    FINDING_VALIDATED = "finding_validated"
    FINDING_APPROVED = "finding_approved"
    FINDING_REJECTED = "finding_rejected"
    TICKET_CREATED = "ticket_created"
    VENDOR_CREATED = "vendor_created"
    TICKET_VENDOR_ASSIGNED = "ticket_vendor_assigned"
    TICKET_DEADLINE_OVERRIDDEN = "ticket_deadline_overridden"
    REMEDIATION_SUBMITTED = "remediation_submitted"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    TICKET_CLOSED = "ticket_closed"
    ALERT_DELIVERED = "alert_delivered"
    ALERT_DELIVERY_FAILED = "alert_delivery_failed"
    AGENT_EXECUTION_STARTED = "agent_execution_started"
    AGENT_EXECUTION_COMPLETED = "agent_execution_completed"
    AGENT_EXECUTION_FAILED = "agent_execution_failed"
    SCAN_TRIGGERED = "scan_triggered"
    SCAN_QUEUED_DUPLICATE = "scan_queued_duplicate"
    SITE_CREATED = "site_created"
    SITE_SCHEDULE_UPDATED = "site_schedule_updated"
    SITE_EXCLUSIONS_UPDATED = "site_exclusions_updated"
    AUTHORIZATION_RECORD_ADDED = "authorization_record_added"