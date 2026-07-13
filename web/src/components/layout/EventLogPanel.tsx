import { Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useProjectStore, type EventLogEntry } from '@/store/projectStore'
import { useT, type TranslationKey } from '@/lib/i18n'

const LEVEL_KEY: Record<EventLogEntry['level'], TranslationKey> = {
  info:  'event_log_level_info',
  warn:  'event_log_level_warn',
  error: 'event_log_level_error',
}

export function EventLogPanel() {
  const t = useT()
  const locale = useProjectStore((s) => s.appSettings.locale)
  const logs = useProjectStore((s) => s.eventLogs)
  const clearEventLogs = useProjectStore((s) => s.clearEventLogs)

  return (
    <section className="flex h-full flex-col bg-background">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {t('event_log_title')}
        </h3>
        <Button variant="ghost" size="sm" className="h-6 gap-1 text-xs" onClick={clearEventLogs}>
          <Trash2 className="h-3 w-3" />
          {t('event_log_clear')}
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 text-xs">
        {logs.length === 0 ? (
          <p className="text-muted-foreground">{t('event_log_empty')}</p>
        ) : (
          <div className="flex flex-col gap-1">
            {logs
              .slice()
              .reverse()
              .map((log) => (
                <div key={log.id} className="flex items-start gap-2 border-b border-border/60 py-1">
                  <span className="w-16 shrink-0 font-mono text-[10px] text-muted-foreground">
                    {new Date(log.at).toLocaleTimeString(locale)}
                  </span>
                  <span
                    className={`w-10 shrink-0 uppercase text-[10px] ${
                      log.level === 'error'
                        ? 'text-destructive'
                        : log.level === 'warn'
                          ? 'text-yellow-500'
                          : 'text-muted-foreground'
                    }`}
                  >
                    {t(LEVEL_KEY[log.level])}
                  </span>
                  <span className="flex-1 text-foreground">{log.message}</span>
                </div>
              ))}
          </div>
        )}
      </div>
    </section>
  )
}
