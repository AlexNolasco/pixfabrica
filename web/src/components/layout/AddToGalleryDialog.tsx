import { Loader2, X } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { apiPublishToGallery } from '@/lib/galleryApi'
import { projectHasValidationIssues } from '@/lib/invalidClipParams'
import { useT } from '@/lib/i18n'
import { toWebProjectJson } from '@/lib/renderJob'
import { useProjectStore } from '@/store/projectStore'

const SLUG_PATTERN = /^[a-z0-9_-]+$/

/** Match API gallery slug rules; strips spaces and punctuation instead of rejecting. */
export function normalizeGallerySlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function slugFromTitle(title: string): string {
  const base = normalizeGallerySlug(title)
  return base.length > 0 ? base : 'untitled'
}

export function galleryPublishUiEnabled(): boolean {
  return import.meta.env.DEV
}

export function AddToGalleryDialog({
  open,
  onOpenChange,
  onPublished,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPublished?: (info: { category: string; slug: string }) => void
}) {
  const t = useT()
  const titleId = useId()
  const thumbInputRef = useRef<HTMLInputElement>(null)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const metaTitle = useProjectStore((s) => s.meta.title)

  const [category, setCategory] = useState('starters')
  const [slug, setSlug] = useState('')
  const [thumbFile, setThumbFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setSlug(slugFromTitle(metaTitle))
    setError(null)
    setThumbFile(null)
    if (thumbInputRef.current) thumbInputRef.current.value = ''
  }, [metaTitle, open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onOpenChange(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onOpenChange, open, submitting])

  const handleSubmit = async () => {
    const state = useProjectStore.getState()
    const { tracks, sounds } = state
    if (tracks.length === 0 && sounds.length === 0) {
      setError(t('gallery_publish_empty_project'))
      return
    }
    if (
      projectHasValidationIssues(
        {
          tracks: state.tracks,
          projectSettings: state.projectSettings,
          catalogLoadStatus: state.catalogLoadStatus,
          catalogClips: state.catalogClips,
          catalogDetailCache: state.catalogDetailCache,
          locale: state.appSettings.locale,
        },
        state.prepareWarnings,
      )
    ) {
      setError(t('gallery_publish_validation_blocked'))
      return
    }

    const trimmedCategory = normalizeGallerySlug(category)
    const trimmedSlug = normalizeGallerySlug(slug)
    if (
      !trimmedCategory ||
      !trimmedSlug ||
      !SLUG_PATTERN.test(trimmedCategory) ||
      !SLUG_PATTERN.test(trimmedSlug)
    ) {
      setError(t('gallery_publish_invalid_slug'))
      return
    }
    setCategory(trimmedCategory)
    setSlug(trimmedSlug)
    if (!thumbFile) {
      setError(t('gallery_publish_thumb_required'))
      return
    }

    const project = toWebProjectJson({
      meta: state.meta,
      tracks: state.tracks,
      sounds: state.sounds,
      projectSettings: state.projectSettings,
      typography: state.typography,
      colors: state.colors,
      paletteSource: state.paletteSource,
      locale: state.appSettings.locale,
      timelineLayout: state.timelineLayout,
    })

    setSubmitting(true)
    setError(null)
    try {
      const result = await apiPublishToGallery({
        category: trimmedCategory,
        slug: trimmedSlug,
        project,
        thumb: thumbFile,
      })
      appendEventLog(
        'info',
        `${t('gallery_publish_success')}: ${result.category}/${result.slug}`,
      )
      onPublished?.({ category: result.category, slug: result.slug })
      onOpenChange(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : t('gallery_publish_failed')
      setError(message)
      appendEventLog('error', message)
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  const inputClass =
    'w-full rounded border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary/60'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/50 supports-backdrop-filter:backdrop-blur-sm"
        aria-label={t('dialog_cancel')}
        disabled={submitting}
        onClick={() => onOpenChange(false)}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 w-full max-w-md rounded-xl border border-border bg-background shadow-2xl p-5"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold tracking-tight">
              {t('gallery_publish_title')}
            </h2>
            <p className="text-xs text-muted-foreground mt-1">{t('gallery_publish_body')}</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="shrink-0"
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-3">
          <label className="block space-y-1">
            <span className="text-xs font-medium">{t('gallery_publish_category')}</span>
            <input
              className={inputClass}
              value={category}
              disabled={submitting}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="starters"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium">{t('gallery_publish_slug')}</span>
            <input
              className={inputClass}
              value={slug}
              disabled={submitting}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="cozy-night"
            />
          </label>
          <div className="space-y-1">
            <span className="text-xs font-medium">{t('gallery_publish_thumb')}</span>
            <input
              ref={thumbInputRef}
              type="file"
              accept=".webp,.jpg,.jpeg,.png,image/webp,image/jpeg,image/png"
              disabled={submitting}
              className="block w-full text-xs"
              onChange={(e) => setThumbFile(e.target.files?.[0] ?? null)}
            />
          </div>
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            {t('dialog_cancel')}
          </Button>
          <Button type="button" size="sm" disabled={submitting} onClick={() => void handleSubmit()}>
            {submitting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {t('gallery_publish_submitting')}
              </>
            ) : (
              t('gallery_publish_submit')
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
