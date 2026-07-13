export type PrepareWarningItem = {
  kind: 'clip' | 'sound'
  ref_id: string
  clip_type: string
  field: string
  source: string
  code: string
  message: string
}

export function prepareWarningsFingerprint(items: PrepareWarningItem[]): string {
  if (items.length === 0) return ''
  return items
    .map((w) => `${w.kind}:${w.ref_id}:${w.source}`)
    .sort()
    .join('|')
}
