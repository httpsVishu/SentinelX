import type {
  AgentName,
  AlertLevel,
  AlertTriggerType,
  FindingStatus,
  ScanStatus,
  ScanTriggerType,
  Severity,
  TicketStatus,
} from '@/api/types'

// Tailwind only keeps class names it can see as full strings, so every
// class below is written out rather than built from parts.

export const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'informational']

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  informational: 'Informational',
}

export const SEVERITY_TEXT: Record<Severity, string> = {
  critical: 'text-sev-critical',
  high: 'text-sev-high',
  medium: 'text-sev-medium',
  low: 'text-sev-low',
  informational: 'text-sev-info',
}

export const SEVERITY_BG: Record<Severity, string> = {
  critical: 'bg-sev-critical',
  high: 'bg-sev-high',
  medium: 'bg-sev-medium',
  low: 'bg-sev-low',
  informational: 'bg-sev-info',
}

// Hex values for Recharts, which cannot read Tailwind classes.
export const SEVERITY_HEX: Record<Severity, string> = {
  critical: '#B3263A',
  high: '#C45A1C',
  medium: '#C79A24',
  low: '#4D70B8',
  informational: '#7C8498',
}

export const TICKET_STATUS_LABEL: Record<TicketStatus, string> = {
  unassigned: 'Unassigned',
  open: 'Open',
  overdue: 'Overdue',
  fix_submitted_pending_verification: 'Fix submitted, awaiting re-scan',
  verified_closed: 'Verified and closed',
  fix_failed_reopened: 'Fix failed, reopened',
}

export const TICKET_STATUS_TEXT: Record<TicketStatus, string> = {
  unassigned: 'text-tape',
  open: 'text-carbon',
  overdue: 'text-stamp',
  fix_submitted_pending_verification: 'text-ink-soft',
  verified_closed: 'text-ledger',
  fix_failed_reopened: 'text-stamp',
}

export const TICKET_FILTER_OPTIONS: TicketStatus[] = [
  'unassigned',
  'open',
  'overdue',
  'fix_submitted_pending_verification',
  'fix_failed_reopened',
  'verified_closed',
]

export function isTicketLive(status: TicketStatus): boolean {
  return status !== 'verified_closed'
}

export const FINDING_STATUS_LABEL: Record<FindingStatus, string> = {
  raw: 'Raw',
  confirmed: 'Confirmed',
  discarded: 'Discarded as false positive',
  inconclusive: 'Inconclusive',
  needs_manual_review: 'Needs manual verification',
  pending_admin_review: 'Waiting for your review',
  approved: 'Approved',
  rejected: 'Rejected',
}

export const SCAN_STATUS_LABEL: Record<ScanStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

export const SCAN_TRIGGER_LABEL: Record<ScanTriggerType, string> = {
  scheduled: 'Scheduled',
  manual: 'Manual',
  verification: 'Fix verification',
}

export const AGENT_ORDER: AgentName[] = [
  'recon',
  'mapping',
  'assessment',
  'validation',
  'reporting',
  'accountability',
  'verification',
]

export const AGENT_LABEL: Record<AgentName, string> = {
  recon: 'Recon',
  mapping: 'Mapping',
  assessment: 'Assessment',
  validation: 'Validation',
  reporting: 'Reporting',
  accountability: 'Accountability',
  verification: 'Verification',
}

export const ALERT_TRIGGER_LABEL: Record<AlertTriggerType, string> = {
  critical_finding_confirmed: 'Critical finding confirmed',
  high_finding_confirmed: 'High finding confirmed',
  unauthorized_change: 'Unauthorized change',
  deadline_missed: 'Deadline missed',
  verification_failed: 'Fix failed verification',
  scan_failed: 'Scan failed',
  pipeline_failure: 'Pipeline failure',
  ticket_assigned: 'Ticket assigned to you',
  ticket_deadline_changed: 'Deadline changed',
}

export const ALERT_LEVEL_LABEL: Record<AlertLevel, string> = {
  urgent: 'Urgent',
  warning: 'Warning',
  info: 'Info',
}

export const ALERT_LEVEL_TEXT: Record<AlertLevel, string> = {
  urgent: 'text-stamp',
  warning: 'text-tape',
  info: 'text-ink-soft',
}