import { Loader2, Palette } from 'lucide-react'
import { useCallback, useState } from 'react'
import { Button } from '@/components/ui/button'
import { cloneJobColors } from '@/lib/jobColors'
import { mediaFilenameFromSource } from '@/lib/mediaUpload'
import { extractPaletteFromSource } from '@/lib/themePresets'
import { useT } from '@/lib/i18n'
import { useProjectStore } from '@/store/projectStore'

export function BackgroundImageExtractTheme({ source }: { source: string }) {
  const t = useT()
  const applyExtractedPalette = useProjectStore((s) => s.applyExtractedPalette)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleExtract = useCallback(async () => {
    const trimmed = source.trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)
    try {
      const palette = await extractPaletteFromSource(trimmed)
      applyExtractedPalette(cloneJobColors(palette), mediaFilenameFromSource(trimmed))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : t('left_theme_upload_failed'))
    } finally {
      setLoading(false)
    }
  }, [applyExtractedPalette, source, t])

  return (
    <div className="flex flex-col gap-1 rounded border border-border px-2 py-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-full justify-start gap-2 text-xs"
        disabled={loading}
        onClick={() => void handleExtract()}
      >
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
        ) : (
          <Palette className="h-3.5 w-3.5 shrink-0" />
        )}
        {t('prop_extract_theme_from_image')}
      </Button>
      <p className="text-[10px] text-muted-foreground leading-snug">{t('prop_extract_theme_from_image_hint')}</p>
      {error ? <p className="text-[10px] text-destructive leading-snug">{error}</p> : null}
    </div>
  )
}
