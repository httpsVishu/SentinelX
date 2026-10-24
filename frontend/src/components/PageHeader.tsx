import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  intro?: string
  actions?: ReactNode
}

export default function PageHeader({ title, intro, actions }: PageHeaderProps) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b-2 border-ink pb-4">
      <div>
        <h1 className="text-title">{title}</h1>
        {intro && <p className="mt-1 max-w-prose text-ink-soft">{intro}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  )
}