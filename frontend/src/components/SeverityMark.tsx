import type { Severity } from '@/api/types'
import { SEVERITY_BG, SEVERITY_LABEL } from '@/lib/labels'

export default function SeverityMark({ severity }: { severity: Severity }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden="true" className={`inline-block h-3 w-3 ${SEVERITY_BG[severity]}`} />
      <span className="font-semibold">{SEVERITY_LABEL[severity]}</span>
    </span>
  )
}