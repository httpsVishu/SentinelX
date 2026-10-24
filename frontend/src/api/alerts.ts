import { api } from './client'
import type { Alert, AlertLevel, AlertTriggerType } from './types'

export interface AlertFilters {
  siteId?: string
  level?: AlertLevel
  triggerType?: AlertTriggerType
}

function toQuery(filters: AlertFilters) {
  return { site_id: filters.siteId, level: filters.level, trigger_type: filters.triggerType }
}

export const alertsApi = {
  listForDepartment: (filters: AlertFilters = {}) => api.get<Alert[]>('/alerts', toQuery(filters)),
  listMine: (filters: AlertFilters = {}) => api.get<Alert[]>('/alerts/mine', toQuery(filters)),
}