import { api } from './client'
import type { User } from './types'

export interface VendorUserCreate {
  email: string
  password: string
  full_name: string
  vendor_id: string
}

export const usersApi = {
  listForVendor: (vendorId: string) => api.get<User[]>(`/users/vendor/${vendorId}`),
  createVendorUser: (data: VendorUserCreate) => api.post<User>('/users', { ...data, role: 'vendor' }),
}