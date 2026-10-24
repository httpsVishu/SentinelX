import { api } from './client'
import type { Finding, FindingReviewCreate, FindingStatus, Severity } from './types'

// The light shape returned by the list endpoint. It has no proof summary.
export interface FindingListItem {
  id: string
  site_id: string
  title: string
  severity: Severity
  status: FindingStatus
  affected_endpoint: string
  confidence: number
  created_at: string
}

export interface FindingFilters {
  siteId?: string
  status?: FindingStatus
}

export const findingsApi = {
  list: (filters: FindingFilters = {}) =>
    api.get<FindingListItem[]>('/findings', { site_id: filters.siteId, status: filters.status }),
  pendingReview: () => api.get<Finding[]>('/findings/pending-review'),
  get: (id: string) => api.get<Finding>(`/findings/${id}`),
  review: (id: string, data: FindingReviewCreate) => api.post<Finding>(`/findings/${id}/review`, data),
}