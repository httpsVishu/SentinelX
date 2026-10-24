import { ApiError } from '@/api/client'

// The server's own message when there is one, otherwise a plain fallback.
export function messageFrom(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback
}