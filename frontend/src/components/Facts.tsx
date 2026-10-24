import type { ReactNode } from 'react'

export interface Fact {
  label: string
  value: ReactNode
}

// A ruled list of label and value pairs, used on finding, ticket and site pages.
export default function Facts({ items }: { items: Fact[] }) {
  return (
    <dl className="grid gap-x-8 sm:grid-cols-[11rem_1fr]">
      {items.map((item) => (
        <div key={item.label} className="contents">
          <dt className="border-t border-ink/15 pt-3 text-sm font-semibold text-ink-soft sm:pb-3">{item.label}</dt>
          <dd className="pb-3 sm:border-t sm:border-ink/15 sm:pt-3">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}