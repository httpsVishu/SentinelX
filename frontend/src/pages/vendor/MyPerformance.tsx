import { scorecardsApi } from '@/api/scorecards'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import ScorecardList, { hasScorecardHistory } from '@/components/ScorecardList'
import { useAsync } from '@/hooks/useAsync'

export default function MyPerformance() {
  const { data, error, loading, reload } = useAsync(() => scorecardsApi.mine())

  if (loading && !data) return <p className="text-ink-soft">Loading your scorecard</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="Your scorecard did not load"
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

  return (
    <div>
      <PageHeader
        title="My performance"
        intro="Worked out from verified tickets only. Your department admin sees the same numbers, and nobody can edit them."
      />
      {hasScorecardHistory(data) ? (
        <ScorecardList card={data} />
      ) : (
        <Notice>
          Not enough history yet. Your scorecard starts once you have a ticket that is closed or overdue.
        </Notice>
      )}
    </div>
  )
}