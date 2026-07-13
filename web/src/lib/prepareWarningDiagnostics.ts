import { prepareWarningsFingerprint, type PrepareWarningItem } from '@/lib/prepareWarningTypes'

let lastReportedPrepareWarningsFingerprint: string | null = null

export function resetPrepareWarningDiagnostics(): void {
  lastReportedPrepareWarningsFingerprint = null
}

export function shouldLogPrepareWarnings(items: PrepareWarningItem[]): boolean {
  const fingerprint = prepareWarningsFingerprint(items)
  if (fingerprint === lastReportedPrepareWarningsFingerprint) {
    return false
  }
  lastReportedPrepareWarningsFingerprint = fingerprint
  return items.length > 0
}
