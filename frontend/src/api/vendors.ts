import { api } from './client'
import type { Vendor, VendorCreate } from './types'

export const vendorsApi = {
  list: () => api.get<Vendor[]>('/vendors'),
  get: (id: string) => api.get<Vendor>(`/vendors/${id}`),
  create: (data: VendorCreate) => api.post<Vendor>('/vendors', data),
  update: (id: string, data: Partial<VendorCreate>) => api.patch<Vendor>(`/vendors/${id}`, data),
  remove: (id: string) => api.del(`/vendors/${id}`),
}