import { apiDelete, apiPost } from '@/lib/apiClient'

export interface ComposeChatResponse {
  session_id: string
  assistant_message: string
  project: Record<string, unknown> | null
  applied: boolean
  context?: {
    prompt_tokens: number
    num_ctx: number
    fill_ratio: number
  }
}

export interface ComposeJobContext {
  colors?: Record<string, string>
  palette_source?: Record<string, unknown>
}

export async function apiComposeChat(params: {
  session_id?: string
  message: string
  job_context?: ComposeJobContext
}): Promise<ComposeChatResponse> {
  return apiPost<ComposeChatResponse>('/compose/chat', params)
}

export async function apiDeleteComposeSession(sessionId: string): Promise<{ deleted: boolean }> {
  return apiDelete<{ deleted: boolean }>(`/compose/sessions/${encodeURIComponent(sessionId)}`)
}
