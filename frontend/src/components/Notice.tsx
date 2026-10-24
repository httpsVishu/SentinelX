import type { ReactNode } from 'react'

interface NoticeProps {
  tone?: 'error' | 'info'
  title?: string
  children: ReactNode
  action?: ReactNode
}

// Inline message. Errors say what went wrong and what to do next.
export default function Notice({ tone = 'info', title, children, action }: NoticeProps) {
  const toneClass = tone === 'error' ? 'border-stamp bg-stamp-wash' : 'border-carbon bg-carbon-wash'

  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`border-l-4 px-4 py-3 ${toneClass}`}>
      {title && <p className="font-bold">{title}</p>}
      <div>{children}</div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}