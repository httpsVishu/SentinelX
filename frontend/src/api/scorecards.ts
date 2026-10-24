import { api } from './client'
import type { SLAConfig, VendorScorecard } from './types'

export const scorecardsApi = {
  forVendor: (vendorId: string) => api.get<VendorScorecard>(`/scorecards/${vendorId}`),
  mine: () => api.get<VendorScorecard>('/scorecards/mine'),
}

export const slaApi = {
  get: () => api.get<SLAConfig>('/schedules/sla'),
  update: (data: Omit<SLAConfig, 'effective_from'>) => api.put<SLAConfig>('/schedules/sla', data),
}