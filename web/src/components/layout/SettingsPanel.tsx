import { X } from 'lucide-react'
import { useProjectStore, type ThumbnailExportResolution, type VideoEncoder } from '@/store/projectStore'
import { useT } from '@/lib/i18n'

export function SettingsPanel() {
  const t = useT()
  const setSettingsPanelOpen = useProjectStore((s) => s.setSettingsPanelOpen)
  const layoutPrefs = useProjectStore((s) => s.appLayoutPrefs)
  const setLayoutPrefs = useProjectStore((s) => s.setLayoutPrefs)
  const thumbnailExportResolution = useProjectStore(
    (s) => s.appSettings.thumbnailExportResolution,
  )
  const renderParallelism = useProjectStore((s) => s.appSettings.renderParallelism)
  const videoEncoder = useProjectStore((s) => s.appSettings.videoEncoder)
  const setAppSettings = useProjectStore((s) => s.setAppSettings)

  return (
    <aside
      data-transport-block
      className="flex h-full w-[280px] shrink-0 flex-col border-l border-border bg-background"
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <h2 className="text-sm font-semibold">{t('settings_panel_title')}</h2>
        <button
          type="button"
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          onClick={() => setSettingsPanelOpen(false)}
          aria-label={t('settings_panel_title')}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3 text-xs">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {t('settings_section_layout')}
        </p>
        <NumberField
          label={t('settings_layout_left')}
          value={layoutPrefs.leftWidthPct}
          min={12}
          max={28}
          onChange={(v) => setLayoutPrefs({ leftWidthPct: v })}
        />
        <NumberField
          label={t('settings_layout_right')}
          value={layoutPrefs.rightWidthPct}
          min={20}
          max={38}
          onChange={(v) => setLayoutPrefs({ rightWidthPct: v })}
        />
        <NumberField
          label={t('settings_layout_preview_region')}
          value={layoutPrefs.previewHeightPct}
          min={8}
          max={50}
          onChange={(v) => setLayoutPrefs({ previewHeightPct: v })}
        />
        <p className="pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {t('settings_section_export')}
        </p>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">{t('settings_video_encoder')}</span>
          <select
            className="w-full rounded border border-border bg-background px-2 py-1 text-foreground outline-none focus:border-primary/60"
            value={videoEncoder}
            onChange={(e) =>
              setAppSettings({
                videoEncoder: e.target.value as VideoEncoder,
              })
            }
          >
            <option value="auto">{t('settings_video_encoder_auto')}</option>
            <option value="cpu">{t('settings_video_encoder_cpu')}</option>
            <option value="nvenc">{t('settings_video_encoder_nvenc')}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">{t('settings_render_parallelism')}</span>
          <select
            className="w-full rounded border border-border bg-background px-2 py-1 text-foreground outline-none focus:border-primary/60"
            value={renderParallelism}
            onChange={(e) =>
              setAppSettings({
                renderParallelism: e.target.value as 'single' | 'multi',
              })
            }
          >
            <option value="single">{t('settings_render_parallelism_single')}</option>
            <option value="multi">{t('settings_render_parallelism_multi')}</option>
          </select>
        </label>
        <p className="pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {t('settings_section_preview')}
        </p>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">{t('settings_thumbnail_export')}</span>
          <select
            className="w-full rounded border border-border bg-background px-2 py-1 text-foreground outline-none focus:border-primary/60"
            value={thumbnailExportResolution}
            onChange={(e) =>
              setAppSettings({
                thumbnailExportResolution: e.target.value as ThumbnailExportResolution,
              })
            }
          >
            <option value="full">{t('settings_thumbnail_export_full')}</option>
            <option value="preview">{t('settings_thumbnail_export_preview')}</option>
          </select>
        </label>
      </div>
    </aside>
  )
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
}) {
  return (
    <label className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        className="w-20 rounded border border-border bg-background px-2 py-1 text-right outline-none focus:border-primary/60"
        value={Math.round(value)}
        onChange={(e) => {
          const n = Number(e.target.value)
          if (Number.isNaN(n)) return
          let next = n
          if (min != null) next = Math.max(min, next)
          if (max != null) next = Math.min(max, next)
          onChange(next)
        }}
      />
    </label>
  )
}
