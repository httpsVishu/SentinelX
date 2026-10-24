import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import type { Severity } from '@/api/types'
import { SEVERITY_BG, SEVERITY_HEX, SEVERITY_LABEL, SEVERITY_ORDER } from '@/lib/labels'

interface SeverityBreakdownProps {
  counts: Record<Severity, number>
}

// One stacked bar, not a pie. The legend below carries the exact numbers,
// so the chart is never the only place a count appears.
export default function SeverityBreakdown({ counts }: SeverityBreakdownProps) {
  const total = SEVERITY_ORDER.reduce((sum, severity) => sum + counts[severity], 0)

  if (total === 0) {
    return <p className="text-ink-soft">No unresolved tickets.</p>
  }

  const data = [{ label: 'Unresolved tickets', ...counts }]
  const summary = SEVERITY_ORDER.filter((s) => counts[s] > 0)
    .map((s) => `${counts[s]} ${SEVERITY_LABEL[s].toLowerCase()}`)
    .join(', ')

  return (
    <div>
      <div role="img" aria-label={`Unresolved tickets by severity: ${summary}`} className="h-10 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }} barCategoryGap={0}>
            <XAxis type="number" hide domain={[0, total]} />
            <YAxis type="category" dataKey="label" hide />
            {SEVERITY_ORDER.map((severity) => (
              <Bar
                key={severity}
                dataKey={severity}
                stackId="severity"
                fill={SEVERITY_HEX[severity]}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-1">
        {SEVERITY_ORDER.map((severity) => (
          <li key={severity} className="flex items-center gap-2 tnum">
            <span aria-hidden="true" className={`inline-block h-3 w-3 ${SEVERITY_BG[severity]}`} />
            <span>
              {SEVERITY_LABEL[severity]} <strong>{counts[severity]}</strong>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}