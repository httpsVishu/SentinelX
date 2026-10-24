import type { UserRole } from '@/api/types'

export function homePathFor(role: UserRole): string {
  return role === 'admin' ? '/admin' : '/vendor'
}