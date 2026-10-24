import { api } from './client'
import type { AgentExecution, Scan } from './types'

export const scansApi = {
  list: (siteId?: string) => api.get<Scan[]>('/scans', { site_id: siteId }),
  get: (id: string) => api.get<Scan>(`/scans/${id}`),
  trigger: (siteId: string, note?: string) => api.post<Scan>(`/scans/${siteId}/trigger`, { note: note ?? null }),
  executions: (scanId: string) => api.get<AgentExecution[]>(`/scans/${scanId}/executions`),
  execution: (executionId: string) => api.get<AgentExecution>(`/agent-executions/${executionId}`),
}