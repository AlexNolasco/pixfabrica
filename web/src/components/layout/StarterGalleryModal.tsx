import { Loader2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  fetchGalleryList,
  fetchGalleryStarter,
  galleryItemKey,
  galleryThumbnailSrc,
  type GalleryCategory,
  type GalleryItem,
} from '@/lib/galleryApi'
import { useT } from '@/lib/i18n'
import { parseProjectJsonValue, type ProjectImportPayload } from '@/lib/projectFileActions'
import { useProjectStore } from '@/store/projectStore'

function GalleryCardSkeleton() {
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="aspect-video bg-muted animate-pulse" />
      <div className="p-3 space-y-2">
        <div className="h-3.5 w-2/3 rounded bg-muted animate-pulse" />
        <div className="h-3 w-full rounded bg-muted animate-pulse" />
        <div className="h-3 w-4/5 rounded bg-muted animate-pulse" />
      </div>
    </div>
  )
}

function GallerySkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {Array.from({ length: 6 }, (_, i) => (
        <GalleryCardSkeleton key={i} />
      ))}
    </div>
  )
}

function GalleryCard({
  item,
  loading,
  onSelect,
}: {
  item: GalleryItem
  loading: boolean
  onSelect: (item: GalleryItem) => void
}) {
  return (
    <button
      type="button"
      disabled={loading}
      className="group rounded-lg border border-border overflow-hidden text-left transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-60"
      onClick={() => onSelect(item)}
    >
      <div className="relative aspect-video bg-muted overflow-hidden">
        <img
          src={galleryThumbnailSrc(item.category, item.id)}
          alt=""
          className="h-full w-full object-cover"
          loading="lazy"
        />
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-background/60">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : null}
      </div>
      <div className="p-3">
        <h3 className="text-sm font-medium leading-snug line-clamp-1">{item.title}</h3>
        {item.description ? (
          <p className="mt-1 text-xs text-muted-foreground leading-snug line-clamp-2">
            {item.description}
          </p>
        ) : null}
      </div>
    </button>
  )
}

function GallerySection({
  category,
  loadingItemKey,
  onSelect,
}: {
  category: GalleryCategory
  loadingItemKey: string | null
  onSelect: (item: GalleryItem) => void
}) {
  return (
    <section>
      <h2 className="text-sm font-semibold tracking-tight text-foreground mb-3">
        {category.label}
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {category.items.map((item) => (
          <GalleryCard
            key={galleryItemKey(item)}
            item={item}
            loading={loadingItemKey === galleryItemKey(item)}
            onSelect={onSelect}
          />
        ))}
      </div>
    </section>
  )
}

export function StarterGalleryModal({
  open,
  onOpenChange,
  onStarterSelected,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStarterSelected: (payload: ProjectImportPayload) => void
}) {
  const t = useT()
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const [categories, setCategories] = useState<GalleryCategory[]>([])
  const [loadStatus, setLoadStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [loadingItemKey, setLoadingItemKey] = useState<string | null>(null)

  const loadGallery = useCallback(async () => {
    setLoadStatus('loading')
    try {
      const data = await fetchGalleryList()
      setCategories(data.categories)
      setLoadStatus('ready')
    } catch (err) {
      setCategories([])
      setLoadStatus('error')
      appendEventLog(
        'error',
        err instanceof Error ? err.message : t('gallery_load_error'),
      )
    }
  }, [appendEventLog, t])

  useEffect(() => {
    if (!open) {
      setLoadStatus('idle')
      setLoadingItemKey(null)
      return
    }
    void loadGallery()
  }, [loadGallery, open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && loadingItemKey === null) {
        onOpenChange(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [loadingItemKey, onOpenChange, open])

  const handleSelect = useCallback(
    async (item: GalleryItem) => {
      const key = galleryItemKey(item)
      setLoadingItemKey(key)
      try {
        const data = await fetchGalleryStarter(item.category, item.id)
        const result = parseProjectJsonValue(data, `${item.category}/${item.id}.json`)
        if (!result.ok) {
          appendEventLog('warn', `${item.title}: ${t(result.messageKey)}`)
          return
        }
        onStarterSelected(result.payload)
      } catch (err) {
        appendEventLog(
          'error',
          err instanceof Error ? err.message : t('gallery_item_load_error'),
        )
      } finally {
        setLoadingItemKey(null)
      }
    },
    [appendEventLog, onStarterSelected, t],
  )

  if (!open) return null

  const isEmpty =
    loadStatus === 'ready' &&
    (categories.length === 0 || categories.every((c) => c.items.length === 0))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/50 supports-backdrop-filter:backdrop-blur-sm"
        aria-label={t('gallery_close')}
        onClick={() => {
          if (loadingItemKey === null) onOpenChange(false)
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="starter-gallery-title"
        className="relative z-10 flex flex-col w-[95vw] h-[95vh] max-w-6xl rounded-xl border border-border bg-background shadow-2xl overflow-hidden"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4 shrink-0">
          <div className="min-w-0">
            <h1 id="starter-gallery-title" className="text-lg font-semibold tracking-tight">
              {t('gallery_title')}
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">{t('gallery_subtitle')}</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="shrink-0"
            disabled={loadingItemKey !== null}
            onClick={() => onOpenChange(false)}
            title={t('gallery_close')}
          >
            <X className="h-4 w-4" />
          </Button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5">
          {loadStatus === 'loading' && <GallerySkeleton />}
          {loadStatus === 'error' && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <p className="text-sm text-muted-foreground">{t('gallery_load_error')}</p>
              <Button type="button" variant="outline" size="sm" onClick={() => void loadGallery()}>
                {t('gallery_retry')}
              </Button>
            </div>
          )}
          {isEmpty && (
            <p className="text-sm text-muted-foreground text-center py-16">{t('gallery_empty')}</p>
          )}
          {loadStatus === 'ready' && !isEmpty && (
            <div className="space-y-8">
              {categories.map((category) => (
                <GallerySection
                  key={category.id}
                  category={category}
                  loadingItemKey={loadingItemKey}
                  onSelect={(item) => void handleSelect(item)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
