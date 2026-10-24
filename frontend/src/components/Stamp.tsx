import type { ReactNode } from 'react'

type StampTone = 'stamp' | 'ledger' | 'tape' | 'ink'

const TONE_CLASS: Record<StampTone, string> = {
  stamp: 'text-stamp',
  ledger: 'text-ledger',
  tape: 'text-tape',
  ink: 'text-ink-soft',
}

interface StampProps {
  tone: StampTone
  children: ReactNode
  // Plays the press-down animation once. Use on a ticket page, not in lists.
  animate?: boolean
}

export default function Stamp({ tone, children, animate = false }: StampProps) {
  return (
    <span className={`stamp ${TONE_CLASS[tone]} ${animate ? 'stamp-in' : ''}`}>{children}</span>
  )
}