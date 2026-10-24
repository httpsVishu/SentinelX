import { api } from './client'
import type { Ticket, TicketAssignUpdate, TicketListItem, VendorTicketRow } from './types'

export const ticketsApi = {
  // Admin
  list: () => api.get<TicketListItem[]>('/tickets'),
  get: (id: string) => api.get<Ticket>(`/tickets/${id}`),
  assign: (id: string, data: TicketAssignUpdate) => api.post<Ticket>(`/tickets/${id}/assign`, data),
  reverify: (id: string) => api.post<Ticket>(`/tickets/${id}/reverify`),

  // Vendor
  mine: () => api.get<VendorTicketRow[]>('/tickets/mine'),
  mineById: (id: string) => api.get<VendorTicketRow>(`/tickets/mine/${id}`),
  remediate: (id: string, note: string) => api.post<VendorTicketRow>(`/tickets/mine/${id}/remediate`, { note }),
}