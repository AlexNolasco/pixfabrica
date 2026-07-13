import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useT } from '@/lib/i18n'
import { useProjectStore } from '@/store/projectStore'

export function ComposeLauncher() {
  const t = useT()
  const composePanelOpen = useProjectStore((s) => s.composePanelOpen)
  const composeHealth = useProjectStore((s) => s.composeHealth)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const openComposePanel = useProjectStore((s) => s.openComposePanel)
  const setLayoutPrefs = useProjectStore((s) => s.setLayoutPrefs)

  const composeReady =
    apiConnectionStatus === 'connected' && composeHealth?.ready === true

  const handleOpen = () => {
    openComposePanel()
    setLayoutPrefs({ rightCollapsed: false })
  }

  return (
    <section className="flex flex-col border-b border-border shrink-0 px-3 py-3">
      <Button
        type="button"
        variant={composePanelOpen ? 'secondary' : 'outline'}
        size="sm"
        className="h-8 w-full justify-start text-xs gap-2"
        onClick={handleOpen}
        disabled={!composeReady}
        title={!composeReady ? t('compose_open_disabled') : undefined}
      >
        <Sparkles className="w-3.5 h-3.5 shrink-0" />
        {composePanelOpen ? t('compose_open_active') : t('compose_open')}
      </Button>
      {!composeReady ? (
        <p className="mt-1.5 text-[10px] text-muted-foreground leading-snug">
          {t('compose_open_disabled_hint')}
        </p>
      ) : null}
    </section>
  )
}
