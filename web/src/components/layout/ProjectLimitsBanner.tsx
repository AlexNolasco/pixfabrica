import { AlertTriangle } from 'lucide-react'
import { useMemo } from 'react'
import { formatLimitViolation, getProjectLimitViolations } from '@/lib/projectLimits'
import { useProjectStore } from '@/store/projectStore'

export function ProjectLimitsBanner() {
  const tracks = useProjectStore((s) => s.tracks)
  const sounds = useProjectStore((s) => s.sounds)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const locale = useProjectStore((s) => s.appSettings.locale)

  const meta = useProjectStore((s) => s.meta)
  const violations = useMemo(
    () => getProjectLimitViolations(tracks, sounds, serverConfig, meta),
    [tracks, sounds, serverConfig, meta],
  )

  if (violations.length === 0) return null

  return (
    <div
      className="flex shrink-0 items-start gap-2 border-b border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-950 dark:text-amber-100"
      role="status"
    >
      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
      <ul className="min-w-0 flex-1 space-y-0.5">
        {violations.map((v, i) => (
          <li key={`${v.code}-${v.trackId ?? i}`}>
            {formatLimitViolation(v, locale)}
          </li>
        ))}
      </ul>
    </div>
  )
}
