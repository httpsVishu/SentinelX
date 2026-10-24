// Mirrors backend/app/models/enums.py and backend/app/schemas/*.py.
// Enum values must match the backend strings exactly.

export type UserRole = 'admin' | 'vendor'

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'informational'

export type FindingStatus =
  | 'raw'
  | 'confirmed'
  | 'discarded'
  | 'inconclusive'
  | 'needs_manual_review'
  | 'pending_admin_review'
  | 'approved'
  | 'rejected'

export type TicketStatus =
  | 'unassigned'
  | 'open'
  | 'overdue'
  | 'fix_submitted_pending_verification'
  | 'verified_closed'
  | 'fix_failed_reopened'

export type DeadlineSource = 'auto' | 'override'
export type ScanTriggerType = 'scheduled' | 'manual' | 'verification'
export type ScanStatus = 'queued' | 'running' | 'completed' | 'failed'

export type AgentName =
  | 'recon'
  | 'mapping'
  | 'assessment'
  | 'validation'
  | 'reporting'
  | 'accountability'
  | 'verification'

export type AgentExecutionStatus = 'running' | 'succeeded' | 'failed'
export type ReviewDecision = 'approve' | 'reject'
export type VerificationResult = 'passed' | 'failed'

export type AlertTriggerType =
  | 'critical_finding_confirmed'
  | 'high_finding_confirmed'
  | 'unauthorized_change'
  | 'deadline_missed'
  | 'verification_failed'
  | 'scan_failed'
  | 'pipeline_failure'
  | 'ticket_assigned'
  | 'ticket_deadline_changed'

export type AlertLevel = 'urgent' | 'warning' | 'info'
export type AlertDeliveryStatus = 'pending' | 'delivered' | 'failed' | 'suppressed'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  department_id: string
  vendor_id: string | null
  muted_trigger_types: string[]
  created_at: string
  last_login_at: string | null
}

export interface Site {
  id: string
  department_id: string
  name: string
  url: string
  vendor_id: string | null
  scan_frequency_days: number
  excluded_paths: string[]
  is_active: boolean
  is_gov_in: boolean
  created_at: string
  last_scanned_at: string | null
}

export interface SiteCreate {
  name: string
  url: string
  vendor_id?: string | null
  scan_frequency_days?: number
  excluded_paths?: string[]
  is_gov_in?: boolean
}

export interface AuthorizationRecord {
  id: string
  site_id: string
  document_reference: string
  notes: string | null
  granted_by_user_id: string
  granted_at: string
  created_at: string
}

export interface AuthorizationRecordCreate {
  document_reference: string
  notes?: string | null
  granted_at: string
}

export interface Vendor {
  id: string
  department_id: string
  name: string
  contact_email: string
  contact_phone: string | null
  created_at: string
}

export interface VendorCreate {
  name: string
  contact_email: string
  contact_phone?: string | null
}

export interface Finding {
  id: string
  site_id: string
  scan_id: string
  title: string
  description: string
  severity: Severity
  owasp_category: string | null
  confidence: number
  affected_endpoint: string
  status: FindingStatus
  poc_summary: string | null
  plain_language_report: string | null
  remediation_guidance: string | null
  validated_at: string | null
  created_at: string
}

export interface FindingReviewCreate {
  decision: ReviewDecision
  reason?: string | null
}

export interface RemediationSubmission {
  id: string
  ticket_id: string
  vendor_user_id: string
  note: string
  submitted_at: string
}

export interface VerificationRecord {
  id: string
  ticket_id: string
  scan_id: string
  result: VerificationResult
  notes: string | null
  verified_at: string
}

export interface TicketListItem {
  id: string
  site_id: string
  vendor_id: string | null
  severity: Severity
  status: TicketStatus
  deadline: string
  created_at: string
}

export interface Ticket extends TicketListItem {
  finding_id: string
  suggested_deadline: string
  deadline_source: DeadlineSource
  override_reason: string | null
  closed_at: string | null
  remediation_submissions: RemediationSubmission[]
  verification_records: VerificationRecord[]
}

export interface VendorTicket {
  id: string
  site_id: string
  severity: Severity
  status: TicketStatus
  deadline: string
  created_at: string
  plain_language_report: string | null
  remediation_guidance: string | null
  affected_endpoint: string | null
  remediation_submissions: RemediationSubmission[]
}

// The vendor endpoints also return the site name, because vendors cannot
// read the Admin-only sites list.
export type VendorTicketRow = VendorTicket & { site_name: string | null }

export interface TicketAssignUpdate {
  vendor_id?: string | null
  deadline_override?: string | null
  override_reason?: string | null
}

export interface Scan {
  id: string
  site_id: string
  trigger_type: ScanTriggerType
  status: ScanStatus
  target_scope: string[] | null
  verification_ticket_id: string | null
  triggered_by_user_id: string | null
  error_message: string | null
  queued_at: string
  started_at: string | null
  completed_at: string | null
}

export interface AgentExecution {
  id: string
  scan_id: string
  agent_name: AgentName
  status: AgentExecutionStatus
  input_snapshot: Record<string, unknown>
  output_snapshot: Record<string, unknown> | null
  error_message: string | null
  started_at: string
  completed_at: string | null
}

export interface Alert {
  id: string
  trigger_type: AlertTriggerType
  level: AlertLevel
  site_id: string | null
  ticket_id: string | null
  finding_id: string | null
  recipient_user_id: string
  message: string
  delivery_status: AlertDeliveryStatus
  delivery_channel: string | null
  delivery_error: string | null
  created_at: string
  delivered_at: string | null
}

export interface VendorScorecard {
  vendor_id: string
  vendor_name: string
  fix_rate: number
  avg_response_time_hours: number | null
  missed_deadlines: number
  repeat_vulnerabilities: number
  verified_ticket_count: number
  overdue_ticket_count: number
  total_ticket_count: number
}

export interface SLAConfig {
  critical_days: number
  high_days: number
  medium_days: number
  low_days: number
  effective_from: string
}