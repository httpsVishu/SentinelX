import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { scansApi } from '@/api/scans'
import { sitesApi } from '@/api/sites'
import type { AgentExecution } from '@/api/types'
import Facts from '@/components/Facts'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import { useAsync } from '@/hooks/useAsync'
import { formatDateTime } from '@/lib/format'
import { AGENT_LABEL, SCAN_STATUS_LABEL, SCAN_TRIGGER_LABEL } from '@/lib/labels'

const POLL_MS = 3000

async function loadScan(id: string) {
  const scan = await scansApi.get(id)
  const [site, executions] = await Promise.all([sitesApi.get(scan.site_id), scansApi.executions(id)])
  return { scan, site, executions }
}

function secondsBetween(startIso: string, endIso: string | null): string {
  if (!endIso) return 'Still running'
  const seconds = Math.max(0, Math.round((new Date(endIso).getTime() - new Date(startIso).getTime()) / 1000))
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${seconds % 60} s`
}

// Each agent writes a short summary or notes line into its output.
function summarize(execution: AgentExecution): string | null {
  const output = execution.output_snapshot
  if (!output) return null
  for (const key of ['summary', 'notes']) {
    const value = output[key]
    if (typeof value === 'string' && value.trim() !== '') return value
  }
  return null
}

const EXECUTION_STATUS: Record<AgentExecution['status'], { label: string; tone: string }> = {
  running: { label: 'Running', tone: 'text-carbon' },
  succeeded: { label: 'Done', tone: 'text-ledger' },
  failed: { label: 'Failed', tone: 'text-stamp' },
}

export default function ScanDetail() {
  const { id = '' } = useParams()
  const { data, error, loading, reload } = useAsync(() => loadScan(id), [id])

  const active = data?.scan.status === 'queued' || data?.scan.status === 'running'

  // Refresh while the scan is still moving, then stop.
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(reload, POLL_MS)
    return () => window.clearInterval(timer)
  }, [active, reload])

  if (loading && !data) return <p className="text-ink-soft">Loading the scan</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="The scan did not load"
        action={
          <button type="button" className="btn btn-quiet" onClick={reload}>
            Try again
          </button>
        }
      >
        {error}
      </Notice>
    )
  }

  const { scan, site, executions } = data

  return (
    <div>
      <p className="mb-4">
        <Link to="/admin/scans">Back to scans</Link>
      </p>

      <PageHeader title={`${SCAN_TRIGGER_LABEL[scan.trigger_type]} scan of ${site.name}`} intro={site.url} />

      <div className="space-y-12">
        {scan.status === 'failed' && (
          <Notice tone="error" title="This scan failed">
            {scan.error_message ?? 'No reason was recorded.'} The site was not scanned. An alert went to the department admins.
          </Notice>
        )}
        {active && <Notice>This scan is {SCAN_STATUS_LABEL[scan.status].toLowerCase()}. The page refreshes by itself.</Notice>}

        <Facts
          items={[
            { label: 'Result', value: SCAN_STATUS_LABEL[scan.status] },
            { label: 'Site', value: <Link to={`/admin/sites/${site.id}`}>{site.name}</Link> },
            { label: 'Queued', value: <span className="tnum">{formatDateTime(scan.queued_at)}</span> },
            { label: 'Started', value: <span className="tnum">{formatDateTime(scan.started_at)}</span> },
            { label: 'Finished', value: <span className="tnum">{formatDateTime(scan.completed_at)}</span> },
            {
              label: 'Limited to',
              value: scan.target_scope && scan.target_scope.length > 0 ? <code>{scan.target_scope.join(', ')}</code> : 'The whole site, minus excluded paths',
            },
            ...(scan.verification_ticket_id
              ? [{ label: 'Checking a fix for', value: <Link to={`/admin/tickets/${scan.verification_ticket_id}`}>Open the ticket</Link> }]
              : []),
          ]}
        />

        <section>
          <h2 className="text-title mb-1">What each agent did</h2>
          <p className="mb-5 max-w-prose text-ink-soft">
            In the order they ran. Open one to see what it was given and what it returned.
          </p>

          {executions.length === 0 ? (
            <p className="text-ink-soft">{active ? 'No agent has started yet.' : 'No agent ran for this scan.'}</p>
          ) : (
            <ol className="max-w-3xl">
              {executions.map((execution) => {
                const state = EXECUTION_STATUS[execution.status]
                const summary = summarize(execution)
                return (
                  <li key={execution.id} className="border-t border-ink/15 py-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h3 className="text-xl">{AGENT_LABEL[execution.agent_name]}</h3>
                      <p className="text-sm tnum">
                        <span className={`font-semibold ${state.tone}`}>{state.label}</span>
                        <span className="text-ink-soft"> in {secondsBetween(execution.started_at, execution.completed_at)}</span>
                      </p>
                    </div>
                    <p className="text-sm text-ink-faint tnum">{formatDateTime(execution.started_at)}</p>

                    {summary && <p className="mt-2 max-w-prose">{summary}</p>}
                    {execution.error_message && (
                      <p className="mt-2 max-w-prose font-semibold text-stamp">{execution.error_message}</p>
                    )}

                    <details className="mt-3">
                      <summary className="cursor-pointer text-carbon">Show input and output</summary>
                      <div className="mt-3 space-y-3">
                        <div>
                          <p className="mb-1 text-sm font-semibold text-ink-soft">Input</p>
                          <pre className="max-h-72 overflow-auto bg-paper-raised p-3 text-xs">{JSON.stringify(execution.input_snapshot, null, 2)}</pre>
                        </div>
                        <div>
                          <p className="mb-1 text-sm font-semibold text-ink-soft">Output</p>
                          <pre className="max-h-72 overflow-auto bg-paper-raised p-3 text-xs">
                            {execution.output_snapshot ? JSON.stringify(execution.output_snapshot, null, 2) : 'No output was recorded.'}
                          </pre>
                        </div>
                      </div>
                    </details>
                  </li>
                )
              })}
            </ol>
          )}
        </section>
      </div>
    </div>
  )
}