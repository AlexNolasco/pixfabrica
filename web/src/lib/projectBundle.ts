import { apiFetch, ApiHttpError } from '@/lib/apiClient'
import type { WebProjectJson } from '@/lib/renderJob'

export interface BundleImportResponse {
  project: WebProjectJson
  import_bundle_id: string
}

export interface BundleExportMissingError extends Error {
  code: 'missing_assets'
  missingFiles: string[]
}

function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) return null
  const quoted = /filename="([^"]+)"/.exec(header)
  if (quoted?.[1]) return quoted[1]
  const bare = /filename=([^;]+)/.exec(header)
  return bare?.[1]?.trim() ?? null
}

async function readExportError(res: Response): Promise<Error> {
  const text = await res.text()
  try {
    const body = JSON.parse(text) as { detail?: unknown }
    const detail = body.detail
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const record = detail as { code?: string; missing_files?: unknown }
      if (record.code === 'missing_assets' && Array.isArray(record.missing_files)) {
        const missingFiles = record.missing_files.filter((x): x is string => typeof x === 'string')
        const err = new Error('missing_assets') as BundleExportMissingError
        err.code = 'missing_assets'
        err.missingFiles = missingFiles
        return err
      }
    }
    if (typeof detail === 'string') return new Error(detail)
  } catch {
    if (text) return new Error(text)
  }
  return new Error(`export failed (${res.status})`)
}

export async function apiExportProjectBundle(
  project: WebProjectJson,
): Promise<{ blob: Blob; filename: string }> {
  const res = await apiFetch('/project-bundles/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(project),
  })
  if (!res.ok) {
    throw await readExportError(res)
  }
  const filename = parseContentDispositionFilename(res.headers.get('Content-Disposition'))
  return {
    blob: await res.blob(),
    filename: filename ?? 'untitled.pixfabrica.zip',
  }
}

export async function apiImportProjectBundle(file: File): Promise<BundleImportResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await apiFetch('/project-bundles/import', { method: 'POST', body: form })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new ApiHttpError('POST', '/project-bundles/import', res.status, detail || undefined)
  }
  return res.json() as Promise<BundleImportResponse>
}

export function isBundleExportMissingError(err: unknown): err is BundleExportMissingError {
  return (
    err instanceof Error &&
    'code' in err &&
    (err as BundleExportMissingError).code === 'missing_assets' &&
    Array.isArray((err as BundleExportMissingError).missingFiles)
  )
}
