import type { TicketStatus } from '@/api/types'
import Stamp from './Stamp'

// The stamp for the statuses that need one. Other statuses show no stamp.
export default function TicketStamp({ status }: { status: TicketStatus }) {
  switch (status) {
    case 'overdue':
      return <Stamp tone="stamp" animate>Overdue</Stamp>
    case 'verified_closed':
      return <Stamp tone="ledger" animate>Verified</Stamp>
    case 'fix_failed_reopened':
      return <Stamp tone="stamp" animate>Fix failed</Stamp>
    case 'unassigned':
      return <Stamp tone="tape" animate>No vendor</Stamp>
    default:
      return null
  }
}