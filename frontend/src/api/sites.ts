import { api } from './client'
import type { AuthorizationRecord, AuthorizationRecordCreate, Site, SiteCreate } from './types'

export const sitesApi = {
  list: () => api.get<Site[]>('/sites'),
  get: (id: string) => api.get<Site>(`/sites/${id}`),
  create: (data: SiteCreate) => api.post<Site>('/sites', data),

  updateSchedule: (id: string, scanFrequencyDays: number) =>
    api.patch<Site>(`/sites/${id}/schedule`, { scan_frequency_days: scanFrequencyDays }),

  updateExclusions: (id: string, excludedPaths: string[]) =>
    api.patch<Site>(`/sites/${id}/exclusions`, { excluded_paths: excludedPaths }),

  updateVendor: (id: string, vendorId: string | null) =>
    api.patch<Site>(`/sites/${id}/vendor`, { vendor_id: vendorId }),

  updateActive: (id: string, isActive: boolean) =>
    api.patch<Site>(`/sites/${id}/active`, { is_active: isActive }),

  listAuthorizationRecords: (id: string) =>
    api.get<AuthorizationRecord[]>(`/sites/${id}/authorization-records`),

  addAuthorizationRecord: (id: string, data: AuthorizationRecordCreate) =>
    api.post<AuthorizationRecord>(`/sites/${id}/authorization-records`, data),
}