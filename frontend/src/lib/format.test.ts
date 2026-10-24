import { describeDeadline, formatDate, formatHours, formatPercent, runwayProgress } from './format'

describe('describeDeadline', () => {
  const now = new Date('2026-10-10T00:00:00Z')

  it('counts whole days left', () => {
    expect(describeDeadline('2026-10-13T00:00:00Z', now)).toEqual({ label: '3 days left', overdue: false })
  })

  it('uses the singular for one day', () => {
    expect(describeDeadline('2026-10-11T00:00:00Z', now).label).toBe('1 day left')
  })

  it('switches to hours under a day', () => {
    expect(describeDeadline('2026-10-10T05:00:00Z', now).label).toBe('5 h left')
  })

  it('marks a passed deadline as overdue', () => {
    expect(describeDeadline('2026-10-09T19:00:00Z', now)).toEqual({ label: '5 h overdue', overdue: true })
  })
})

describe('runwayProgress', () => {
  it('is half way at the midpoint', () => {
    const progress = runwayProgress('2026-10-01T00:00:00Z', '2026-10-11T00:00:00Z', new Date('2026-10-06T00:00:00Z'))
    expect(progress).toBeCloseTo(0.5)
  })

  it('goes above 1 after the deadline', () => {
    const progress = runwayProgress('2026-10-01T00:00:00Z', '2026-10-11T00:00:00Z', new Date('2026-10-21T00:00:00Z'))
    expect(progress).toBeCloseTo(2)
  })

  it('treats an empty window as used up', () => {
    expect(runwayProgress('2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z')).toBe(1)
  })
})

describe('display helpers', () => {
  it('rounds percentages', () => {
    expect(formatPercent(0.857)).toBe('86%')
  })

  it('shows hours then days', () => {
    expect(formatHours(5)).toBe('5.0 h')
    expect(formatHours(72)).toBe('3.0 days')
  })

  it('says when there is no data', () => {
    expect(formatHours(null)).toBe('No data yet')
    expect(formatDate(null)).toBe('Never')
  })
})