import { apiFetch, apiGet } from '@/lib/apiClient'

export type FontJobStatus = 'pending' | 'completed' | 'failed'

export interface FontJobResponse {
  job_id: string
  status: FontJobStatus
  families: string[]
  warnings: string[]
  error?: string | null
}

export interface FontJobCreateResponse {
  job_id: string
  status: 'pending'
}

export async function apiUploadFont(file: File): Promise<FontJobCreateResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await apiFetch('/fonts', { method: 'POST', body: form })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      detail ? `Font upload failed (${res.status}): ${detail}` : `Font upload failed (${res.status})`,
    )
  }
  return res.json() as Promise<FontJobCreateResponse>
}

export async function apiGetFontJob(jobId: string): Promise<FontJobResponse> {
  return apiGet<FontJobResponse>(`/fonts/jobs/${encodeURIComponent(jobId)}`)
}

export async function pollFontJob(
  jobId: string,
  intervalMs = 400,
  timeoutMs = 120_000,
): Promise<FontJobResponse> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const job = await apiGetFontJob(jobId)
    if (job.status !== 'pending') return job
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  throw new Error('Font install timed out')
}

export const FONT_UPLOAD_ACCEPT = '.ttf,.otf,.zip,font/ttf,font/otf,application/zip,application/x-zip-compressed'
