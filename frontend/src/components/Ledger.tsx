import type { MouseEvent, ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export interface LedgerColumn<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  // The cell that holds the row's link. Only one column should set this.
  primary?: boolean
  className?: string
}

interface LedgerProps<T> {
  caption: string
  rows: T[]
  columns: LedgerColumn<T>[]
  rowKey: (row: T) => string
  rowHref?: (row: T) => string
}

// A ruled register table. No card around it; the ink rule under the header
// and the faint rules between rows are the only structure.
export default function Ledger<T>({ caption, rows, columns, rowKey, rowHref }: LedgerProps<T>) {
  const navigate = useNavigate()

  function handleRowClick(event: MouseEvent<HTMLTableRowElement>, row: T) {
    if (!rowHref) return
    // Let real links and buttons inside the row do their own thing.
    if ((event.target as HTMLElement).closest('a, button, input, select, textarea')) return
    navigate(rowHref(row))
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`border-b-2 border-ink px-3 py-2 text-sm font-semibold text-ink-soft ${column.className ?? ''}`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={(event) => handleRowClick(event, row)}
              className={`border-b border-ink/15 align-top hover:bg-paper-raised ${rowHref ? 'cursor-pointer' : ''}`}
            >
              {columns.map((column) => (
                <td key={column.key} className={`px-3 py-3 ${column.className ?? ''}`}>
                  {column.primary && rowHref ? (
                    <Link to={rowHref(row)} className="font-semibold text-ink no-underline hover:underline">
                      {column.render(row)}
                    </Link>
                  ) : (
                    column.render(row)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}