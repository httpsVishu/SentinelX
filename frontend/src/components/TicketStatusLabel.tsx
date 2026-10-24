import type { TicketStatus } from '@/api/types'
import { TICKET_STATUS_LABEL, TICKET_STATUS_TEXT } from '@/lib/labels'

export default function TicketStatusLabel({ status }: { status: TicketStatus }) {
  return <span className={`font-semibold ${TICKET_STATUS_TEXT[status]}`}>{TICKET_STATUS_LABEL[status]}</span>
}