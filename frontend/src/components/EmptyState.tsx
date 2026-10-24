import type { ReactNode } from 'react'

interface EmptyStateProps {
  heading: string
  children?: ReactNode
  action?: ReactNode
}

// An empty list is a prompt to act, so it names the next step.
export default function EmptyState({ heading, children, action }: EmptyStateProps) {
  return (
    <div className="border-t-2 border-ink py-10">
      <h2 className="text-title">{heading}</h2>
      {children && <p className="mt-2 max-w-prose text-ink-soft">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}