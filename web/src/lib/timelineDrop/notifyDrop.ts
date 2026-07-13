import { tKey } from '@/lib/i18n'
import { useProjectStore } from '@/store/projectStore'
import { useToastStore } from '@/store/toastStore'
import type { TimelineDropFailure } from './types'

function pushWarnToastIfPanelHidden(message: string): void {
  if (useProjectStore.getState().showLogsPanel) return
  useToastStore.getState().pushToast(message, 'warn')
}

function aggregatedFailureToast(failures: TimelineDropFailure[], succeeded: number): string {
  const first = failures[0]!
  const failed = failures.length
  if (succeeded > 0) {
    return tKey('toast_timeline_drop_partial_summary')
      .replace('{ok}', String(succeeded))
      .replace('{failed}', String(failed))
      .replace('{example}', first.name)
      .replace('{detail}', first.message)
  }
  return tKey('toast_timeline_drop_failed_summary')
    .replace('{count}', String(failed))
    .replace('{example}', first.name)
    .replace('{detail}', first.message)
}

/** Event log always; warn toast only when the event panel is hidden. */
export function reportTimelineDropGuard(message: string): void {
  useProjectStore.getState().appendEventLog('warn', message)
  pushWarnToastIfPanelHidden(message)
}

/** Per-file event log always; one aggregated warn toast when the panel is hidden. */
export function reportTimelineDropFailures(
  failures: TimelineDropFailure[],
  succeeded: number,
): void {
  const appendEventLog = useProjectStore.getState().appendEventLog
  for (const failure of failures) {
    appendEventLog('warn', `${failure.name}: ${failure.message}`)
  }
  if (failures.length === 0) return
  pushWarnToastIfPanelHidden(aggregatedFailureToast(failures, succeeded))
}
