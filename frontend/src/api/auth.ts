import { api } from './client'
import type { TokenResponse, User } from './types'

export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }, false),

  me: () => api.get<User>('/users/me'),

  updatePreferences: (mutedTriggerTypes: string[]) =>
    api.patch<User>('/users/me/preferences', { muted_trigger_types: mutedTriggerTypes }),
}