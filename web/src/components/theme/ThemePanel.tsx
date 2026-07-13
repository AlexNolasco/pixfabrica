import { useCallback, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, Dices, ImagePlus, Loader2, Palette } from 'lucide-react'
import { ParamHexColorPicker } from '@/components/params/controls/ParamHexColorPicker'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { PaletteSwatchStrip } from '@/components/theme/PaletteSwatchStrip'
import { apiUploadMedia } from '@/lib/mediaUpload'
import {
  cloneJobColors,
  extractedPaletteBasename,
  paletteSourceLabel,
  presetOptionValue,
  type JobColorPalette,
  type ThemeName,
  type ThemeVariant,
} from '@/lib/jobColors'
import { COLOR_TOKENS, type ColorTokenName } from '@/lib/themeColor'
import { generateJobPalette, resolveGenerationVariant } from '@/lib/generateJobPalette'
import { extractPaletteFromSource } from '@/lib/themePresets'
import { useProjectStore } from '@/store/projectStore'
import { useT } from '@/lib/i18n'

const IMAGE_ACCEPT = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']

const triggerClass =
  'flex w-full items-center gap-2 rounded border border-border bg-muted/50 px-1.5 py-1 text-xs text-foreground outline-none focus:border-primary/60 hover:bg-muted/70'

export function ThemePanel() {
  const t = useT()
  const colors = useProjectStore((s) => s.colors)
  const paletteSource = useProjectStore((s) => s.paletteSource)
  const themePresets = useProjectStore((s) => s.themePresets)
  const themePresetsFallback = useProjectStore((s) => s.themePresetsFallback)
  const applyNamedPreset = useProjectStore((s) => s.applyNamedPreset)
  const applyExtractedPalette = useProjectStore((s) => s.applyExtractedPalette)
  const applyCustomPalette = useProjectStore((s) => s.applyCustomPalette)
  const setJobColor = useProjectStore((s) => s.setJobColor)
  const isPlaying = useProjectStore((s) => s.isPlaying)

  const [sectionOpen, setSectionOpen] = useState(false)
  const [activePicker, setActivePicker] = useState<ColorTokenName | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const selectedValue =
    paletteSource?.type === 'named'
      ? presetOptionValue(paletteSource.theme, paletteSource.variant)
      : paletteSource?.type === 'extracted'
        ? '__extracted__'
        : '__custom__'

  const triggerLabel = useMemo(() => {
    if (paletteSource?.type === 'named') {
      const preset = themePresets.find(
        (p) =>
          p.theme === paletteSource.theme && p.variant === paletteSource.variant,
      )
      return preset?.label ?? paletteSourceLabel(paletteSource, t)
    }
    if (paletteSource?.type === 'extracted') {
      return paletteSourceLabel(paletteSource, t)
    }
    return t('left_theme_custom')
  }, [paletteSource, t, themePresets])

  const triggerTitle =
    paletteSource?.type === 'extracted' && paletteSource.filename
      ? extractedPaletteBasename(paletteSource.filename)
      : undefined

  const onPickPreset = useCallback(
    (theme: ThemeName, variant: ThemeVariant, presetColors: JobColorPalette) => {
      setError(null)
      applyNamedPreset(theme, variant, cloneJobColors(presetColors))
    },
    [applyNamedPreset],
  )

  const onRandomPalette = useCallback(() => {
    setError(null)
    const variant = resolveGenerationVariant(paletteSource, colors)
    applyCustomPalette(generateJobPalette(variant))
  }, [applyCustomPalette, colors, paletteSource])

  const processFile = useCallback(
    async (file: File) => {
      if (!IMAGE_ACCEPT.includes(file.type)) {
        setError(t('left_theme_upload_type_error'))
        return
      }
      setUploading(true)
      setError(null)
      try {
        const uploaded = await apiUploadMedia(file, 'image')
        const palette = await extractPaletteFromSource(uploaded.path)
        applyExtractedPalette(cloneJobColors(palette), file.name)
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : t('left_theme_upload_failed'))
      } finally {
        setUploading(false)
      }
    },
    [applyExtractedPalette, t],
  )

  const onFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      e.target.value = ''
      if (file) void processFile(file)
    },
    [processFile],
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      if (isPlaying || uploading) return
      const file = e.dataTransfer.files?.[0]
      if (file) void processFile(file)
    },
    [isPlaying, processFile, uploading],
  )

  return (
    <section className="flex flex-col border-b border-border shrink-0">
      <button
        type="button"
        className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider select-none hover:bg-muted/30 w-full text-left"
        onClick={() => setSectionOpen((open) => !open)}
      >
        <Palette className="w-3 h-3" />
        {t('left_theme')}
        <ChevronDown
          className={`w-3 h-3 shrink-0 transition-transform ${sectionOpen ? 'rotate-0' : '-rotate-90'}`}
        />
      </button>

      {sectionOpen ? (
        <fieldset
          disabled={isPlaying}
          className={`flex flex-col gap-2 px-3 pb-3 ${isPlaying ? 'opacity-40' : ''}`}
        >
          {themePresetsFallback ? (
            <p className="text-[10px] text-muted-foreground leading-snug">
              {t('left_theme_presets_fallback')}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-1">
            {COLOR_TOKENS.map((token) => (
              <div key={token} className="flex flex-col items-center gap-0.5">
                <ParamHexColorPicker
                  value={colors[token]}
                  open={activePicker === token}
                  onOpenChange={(open) => setActivePicker(open ? token : null)}
                  onChange={(hex) => setJobColor(token, hex)}
                >
                  <span
                    title={token}
                    className="block h-5 w-5 rounded"
                    style={{ backgroundColor: colors[token] }}
                  />
                </ParamHexColorPicker>
                <span className="text-[9px] text-muted-foreground max-w-[3rem] truncate">
                  {token.replace('_', ' ')}
                </span>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{t('left_theme_preset')}</span>
            <div className="flex items-center gap-1">
              <DropdownMenu>
                <DropdownMenuTrigger className={`${triggerClass} min-w-0 flex-1 overflow-hidden`}>
                  <PaletteSwatchStrip palette={colors} size="xs" />
                  <span className="min-w-0 flex-1 truncate text-left" title={triggerTitle}>
                    {triggerLabel}
                  </span>
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                </DropdownMenuTrigger>
                <DropdownMenuContent className="max-h-64 min-w-[var(--radix-dropdown-menu-trigger-width)]" align="start">
                  {themePresets.map((preset) => {
                    const value = presetOptionValue(preset.theme, preset.variant)
                    const isSelected = selectedValue === value
                    return (
                      <DropdownMenuItem
                        key={value}
                        className="flex items-center gap-2 py-1.5 text-xs"
                        onClick={() =>
                          onPickPreset(
                            preset.theme as ThemeName,
                            preset.variant,
                            preset.colors,
                          )
                        }
                      >
                        {isSelected ? (
                          <Check className="h-3.5 w-3.5 shrink-0 text-primary" />
                        ) : (
                          <span className="w-3.5 shrink-0" />
                        )}
                        <PaletteSwatchStrip palette={preset.colors} size="xs" />
                        <span className="min-w-0 flex-1 truncate">{preset.label}</span>
                      </DropdownMenuItem>
                    )
                  })}
                </DropdownMenuContent>
              </DropdownMenu>
              <button
                type="button"
                title={t('left_theme_random')}
                aria-label={t('left_theme_random')}
                className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded border border-border bg-muted/50 text-muted-foreground outline-none hover:bg-muted/70 focus:border-primary/60"
                onClick={onRandomPalette}
              >
                <Dices className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div
            role="button"
            tabIndex={0}
            className={`flex flex-col items-center justify-center gap-1 rounded-md border border-dashed px-2 py-3 text-center transition-colors ${
              dragOver
                ? 'border-primary bg-primary/10'
                : 'border-border bg-muted/20 hover:border-primary/50 hover:bg-muted/40'
            } ${uploading ? 'pointer-events-none opacity-60' : 'cursor-pointer'}`}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click()
            }}
            onDragEnter={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={(e) => {
              e.preventDefault()
              setDragOver(false)
            }}
            onDrop={onDrop}
          >
            {uploading ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : (
              <ImagePlus className="h-4 w-4 text-muted-foreground" />
            )}
            <span className="text-[10px] text-muted-foreground leading-snug">
              {t('left_theme_upload_hint')}
            </span>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept={IMAGE_ACCEPT.join(',')}
            className="hidden"
            onChange={onFileInput}
          />

          {error ? <p className="text-[10px] text-destructive">{error}</p> : null}
        </fieldset>
      ) : null}
    </section>
  )
}
