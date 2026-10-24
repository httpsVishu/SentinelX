// Tests for DeadlineRunway helper functions.
// The component itself renders a visual strip; we test the pure formatting
// and progress functions it relies on rather than snapshot-testing the SVG.

import { describeDeadline, runwayProgress } from '@/lib/format'

describe('runwayProgress (used by DeadlineRunway)', () => {
  it('returns 0.5 at the exact midpoint', () => {
    const progress = runwayProgress(
      '2026-10-01T00:00:00Z',
      '2026-10-11T00:00:00Z',
      new Date('2026-10-06T00:00:00Z'),
    )
    expect(progress).toBeCloseTo(0.5)
  })

  it('returns a value above 1 when today is past the deadline', () => {
    const progress = runwayProgress(
      '2026-10-01T00:00:00Z',
      '2026-10-11T00:00:00Z',
      new Date('2026-10-21T00:00:00Z'),
    )
    expect(progress).toBeCloseTo(2)
  })

  it('returns 1 when start equals end (zero-length window)', () => {
    expect(runwayProgress('2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z')).toBe(1)
  })

  it('returns 0 at the exact start', () => {
    const progress = runwayProgress(
      '2026-10-01T00:00:00Z',
      '2026-10-11T00:00:00Z',
      new Date('2026-10-01T00:00:00Z'),
    )
    expect(progress).toBeCloseTo(0)
  })
})

describe('describeDeadline (used by DeadlineRunway label)', () => {
  const now = new Date('2026-10-10T00:00:00Z')

  it('shows days remaining', () => {
    expect(describeDeadline('2026-10-13T00:00:00Z', now)).toEqual({
      label: '3 days left',
      overdue: false,
    })
  })

  it('uses singular for exactly one day', () => {
    expect(describeDeadline('2026-10-11T00:00:00Z', now).label).toBe('1 day left')
  })

  it('switches to hours for less than a day', () => {
    expect(describeDeadline('2026-10-10T05:00:00Z', now).label).toBe('5 h left')
  })

  it('marks a past deadline as overdue', () => {
    expect(describeDeadline('2026-10-09T19:00:00Z', now)).toEqual({
      label: '5 h overdue',
      overdue: true,
    })
  })
})