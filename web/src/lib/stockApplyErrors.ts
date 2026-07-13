import { tKey } from '@/lib/i18n'
import { formatMaxBytes } from '@/lib/mediaUpload'
import { uploadMaxBytes, type ServerConfig } from '@/lib/serverConfig'
import { useProjectStore } from '@/store/projectStore'
import { useToastStore } from '@/store/toastStore'

export type StockMediaKind = 'photo' | 'video'

const BYTE_LIMIT_RE = /exceeds\s+\d+\s+byte\s+limit/i

export type StockApplyFailureInput =
  | { kind: StockMediaKind; code: 'timeline_full' }
  | { kind: StockMediaKind; code: 'apply_failed'; message: string }

function extractErrorDetail(message: string): string {
  const prefix = message.match(/^Pexels request failed \(\d+\): /)
  if (!prefix) return message
  const body = message.slice(prefix[0].length)
  try {
    const parsed = JSON.parse(body) as { detail?: unknown }
    if (typeof parsed.detail === 'string') return parsed.detail
  } catch {
    return body
  }
  return message
}

function isByteLimitError(detail: string): boolean {
  return BYTE_LIMIT_RE.test(detail) || detail.toLowerCase().includes('byte limit')
}

export function formatStockApplyError(
  input: StockApplyFailureInput,
  serverConfig: Pick<ServerConfig, 'uploadLimits'>,
): string {
  const { kind } = input
  if (input.code === 'timeline_full') {
    return tKey(kind === 'photo' ? 'stock_photos_timeline_full' : 'stock_videos_timeline_full')
  }

  const detail = extractErrorDetail(input.message)
  const uploadKind = kind === 'photo' ? 'image' : 'video'
  const limit = formatMaxBytes(uploadMaxBytes(uploadKind, serverConfig))

  if (isByteLimitError(detail)) {
    return tKey(kind === 'photo' ? 'stock_photos_too_large' : 'stock_videos_too_large').replace(
      '{limit}',
      limit,
    )
  }

  if (detail.startsWith('Pexels request failed')) {
    return tKey(kind === 'photo' ? 'stock_photos_apply_error' : 'stock_videos_apply_error')
  }

  return detail || tKey(kind === 'photo' ? 'stock_photos_apply_error' : 'stock_videos_apply_error')
}

/** Event log always; toast when the logs panel is hidden. */
export function notifyStockApplyFailure(message: string): void {
  const state = useProjectStore.getState()
  state.appendEventLog('error', message)
  if (!state.showLogsPanel) {
    useToastStore.getState().pushToast(message, 'error')
  }
}
