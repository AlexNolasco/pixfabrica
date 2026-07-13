import { Loader2, Search, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useT } from '@/lib/i18n'
import {
  PEXELS_PER_PAGE,
  fetchPexelsSearch,
  pexelsOrientationFromDimensions,
  pexelsPreviewUrl,
  type PexelsPhoto,
} from '@/lib/pexelsApi'
import { applyStockPhotoToProject } from '@/lib/pexelsApply'
import { ingestStockPhotoForParam } from '@/lib/stockParamApply'
import { isPexelsRateLimited, pexelsRateLimitCooldownMs } from '@/lib/pexelsErrors'
import { formatStockApplyError, notifyStockApplyFailure } from '@/lib/stockApplyErrors'
import { FALLBACK_PEXELS_DEFAULT_QUERIES } from '@/lib/serverConfig'
import { useStockPickerStore } from '@/store/stockPickerStore'
import { useProjectStore } from '@/store/projectStore'

const SEARCH_MIN_CHARS = 5
const SEARCH_DEBOUNCE_MS = 400

function chipLabel(query: string): string {
  if (!query) return query
  return query.charAt(0).toUpperCase() + query.slice(1)
}

function PhotoCardSkeleton() {
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="aspect-[4/5] bg-muted animate-pulse" />
      <div className="p-2 space-y-1.5">
        <div className="h-3 w-2/3 rounded bg-muted animate-pulse" />
      </div>
    </div>
  )
}

function SearchSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
      {Array.from({ length: PEXELS_PER_PAGE }, (_, i) => (
        <PhotoCardSkeleton key={i} />
      ))}
    </div>
  )
}

function LoadMoreSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 mt-3">
      {Array.from({ length: 6 }, (_, i) => (
        <PhotoCardSkeleton key={i} />
      ))}
    </div>
  )
}

function PhotoCard({
  photo,
  applying,
  onSelect,
}: {
  photo: PexelsPhoto
  applying: boolean
  onSelect: (photo: PexelsPhoto) => void
}) {
  const preview = pexelsPreviewUrl(photo)
  return (
    <button
      type="button"
      disabled={applying}
      className="group rounded-lg border border-border overflow-hidden text-left transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-60"
      onClick={() => onSelect(photo)}
    >
      <div className="relative aspect-[4/5] bg-muted overflow-hidden">
        {preview ? (
          <img
            src={preview}
            alt={photo.alt ?? ''}
            className="h-full w-full object-cover"
          />
        ) : null}
        {applying ? (
          <div className="absolute inset-0 flex items-center justify-center bg-background/60">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : null}
      </div>
      <div className="p-2 text-[10px] leading-snug text-muted-foreground">
        <a
          href={photo.photographer_url}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-foreground hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {photo.photographer}
        </a>
        {' · '}
        <a
          href={photo.url}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-foreground hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          Pexels
        </a>
      </div>
    </button>
  )
}

export function StockPhotosModal() {
  const t = useT()
  const open = useStockPickerStore((s) => s.photosOpen)
  const photoContext = useStockPickerStore((s) => s.photoContext)
  const closePhotos = useStockPickerStore((s) => s.closePhotos)
  const onOpenChange = useCallback(
    (next: boolean) => {
      if (!next) closePhotos()
    },
    [closePhotos],
  )
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const meta = useProjectStore((s) => s.meta)
  const serverConfig = useProjectStore((s) => s.serverConfig)

  const chipQueries = useMemo(
    () =>
      serverConfig.pexelsDefaultQueries.length > 0
        ? serverConfig.pexelsDefaultQueries
        : [...FALLBACK_PEXELS_DEFAULT_QUERIES],
    [serverConfig.pexelsDefaultQueries],
  )
  const defaultQuery = chipQueries[0] ?? FALLBACK_PEXELS_DEFAULT_QUERIES[0]

  const [searchText, setSearchText] = useState('')
  const [activeQuery, setActiveQuery] = useState<string>(defaultQuery)
  const [photos, setPhotos] = useState<PexelsPhoto[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loadStatus, setLoadStatus] = useState<'idle' | 'loading' | 'loadingMore' | 'ready' | 'error'>('idle')
  const [applyingPhotoId, setApplyingPhotoId] = useState<number | null>(null)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [rateLimitUntil, setRateLimitUntil] = useState<number | null>(null)
  const [, setRateLimitTick] = useState(0)
  const rateLimitUntilRef = useRef<number | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const searchSeqRef = useRef(0)

  const rateLimited = rateLimitUntil != null && Date.now() < rateLimitUntil
  const rateLimitSecondsLeft =
    rateLimitUntil != null ? Math.max(0, Math.ceil((rateLimitUntil - Date.now()) / 1000)) : 0

  const orientation = useMemo(
    () => pexelsOrientationFromDimensions(meta.width, meta.height),
    [meta.width, meta.height],
  )
  const orientationRef = useRef(orientation)

  const runSearch = useCallback(
    async (query: string, pageNum: number, mode: 'replace' | 'append') => {
      if (rateLimitUntilRef.current != null && Date.now() < rateLimitUntilRef.current) {
        return
      }
      const seq = ++searchSeqRef.current
      setLoadStatus(mode === 'append' ? 'loadingMore' : 'loading')
      try {
        const data = await fetchPexelsSearch(query, orientation, pageNum)
        if (seq !== searchSeqRef.current) return
        setPhotos((prev) => (mode === 'append' ? [...prev, ...data.photos] : data.photos))
        setPage(data.page)
        setHasMore(Boolean(data.next_page))
        setLoadStatus('ready')
      } catch (err) {
        if (seq !== searchSeqRef.current) return
        if (isPexelsRateLimited(err)) {
          const cooldownMs = pexelsRateLimitCooldownMs(err)
          const until = Date.now() + cooldownMs
          rateLimitUntilRef.current = until
          setRateLimitUntil(until)
          appendEventLog(
            'warn',
            t('stock_photos_rate_limited').replace(
              '{seconds}',
              String(Math.ceil(cooldownMs / 1000)),
            ),
          )
          if (mode === 'append') {
            setLoadStatus('ready')
          } else {
            setPhotos([])
            setLoadStatus('error')
          }
          return
        }
        if (mode === 'append') {
          setLoadStatus('ready')
        } else {
          setPhotos([])
          setLoadStatus('error')
        }
        appendEventLog(
          'error',
          err instanceof Error ? err.message : t('stock_photos_load_error'),
        )
      }
    },
    [appendEventLog, orientation, t],
  )

  const resetAndSearch = useCallback(
    (query: string) => {
      setApplyError(null)
      setActiveQuery(query)
      setPage(1)
      setHasMore(false)
      void runSearch(query, 1, 'replace')
    },
    [runSearch],
  )

  useEffect(() => {
    if (!open) {
      setLoadStatus('idle')
      setApplyingPhotoId(null)
      setApplyError(null)
      setSearchText('')
      setActiveQuery(defaultQuery)
      setPhotos([])
      setPage(1)
      setHasMore(false)
      rateLimitUntilRef.current = null
      setRateLimitUntil(null)
      orientationRef.current = orientation
      if (debounceRef.current) clearTimeout(debounceRef.current)
      return
    }
    orientationRef.current = orientation
    setSearchText('')
    setActiveQuery(defaultQuery)
    resetAndSearch(defaultQuery)
  }, [defaultQuery, open, resetAndSearch])

  useEffect(() => {
    if (!open) return
    if (orientationRef.current === orientation) return
    orientationRef.current = orientation
    resetAndSearch(activeQuery)
  }, [activeQuery, open, orientation, resetAndSearch])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && applyingPhotoId === null) {
        onOpenChange(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [applyingPhotoId, onOpenChange, open])

  useEffect(() => {
    if (!open || rateLimitUntil == null) return
    const id = window.setInterval(() => {
      if (rateLimitUntilRef.current == null || Date.now() >= rateLimitUntilRef.current) {
        rateLimitUntilRef.current = null
        setRateLimitUntil(null)
      } else {
        setRateLimitTick((n) => n + 1)
      }
    }, 1000)
    return () => clearInterval(id)
  }, [open, rateLimitUntil])

  const handleChipClick = (query: string) => {
    setSearchText('')
    resetAndSearch(query)
  }

  const handleSearchInput = (value: string) => {
    setSearchText(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const trimmed = value.trim()
    if (trimmed.length < SEARCH_MIN_CHARS) return
    debounceRef.current = setTimeout(() => {
      resetAndSearch(trimmed)
    }, SEARCH_DEBOUNCE_MS)
  }

  const handleSearchSubmit = () => {
    const trimmed = searchText.trim()
    if (!trimmed) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    resetAndSearch(trimmed)
  }

  const handleLoadMore = () => {
    if (!hasMore || loadStatus === 'loadingMore') return
    setApplyError(null)
    void runSearch(activeQuery, page + 1, 'append')
  }

  const reportApplyFailure = useCallback(
    (input: Parameters<typeof formatStockApplyError>[0]) => {
      const message = formatStockApplyError(input, serverConfig)
      notifyStockApplyFailure(message)
      setApplyError(message)
    },
    [serverConfig],
  )

  const handleSelect = useCallback(
    async (photo: PexelsPhoto) => {
      setApplyError(null)
      setApplyingPhotoId(photo.id)
      try {
        if (photoContext.mode === 'param') {
          const result = await ingestStockPhotoForParam(
            photo,
            orientation,
            photoContext.target.uploadContext,
            photoContext.target.field,
          )
          if (!result.ok) {
            reportApplyFailure({ kind: 'photo', code: 'apply_failed', message: result.message })
            return
          }
          photoContext.target.onApply(result.result)
          closePhotos()
          return
        }
        const result = await applyStockPhotoToProject(photo, orientation)
        if (!result.ok) {
          reportApplyFailure(
            result.code === 'timeline_full'
              ? { kind: 'photo', code: 'timeline_full' }
              : { kind: 'photo', code: 'apply_failed', message: result.message },
          )
          return
        }
        closePhotos()
      } catch (err) {
        reportApplyFailure({
          kind: 'photo',
          code: 'apply_failed',
          message: err instanceof Error ? err.message : t('stock_photos_apply_error'),
        })
      } finally {
        setApplyingPhotoId(null)
      }
    },
    [closePhotos, orientation, photoContext, reportApplyFailure, t],
  )

  if (!open) return null

  const isEmpty = loadStatus === 'ready' && photos.length === 0
  const usingTypedSearch = searchText.trim().length >= SEARCH_MIN_CHARS

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/50 supports-backdrop-filter:backdrop-blur-sm"
        aria-label={t('stock_photos_close')}
        onClick={() => {
          if (applyingPhotoId === null) onOpenChange(false)
        }}
      />
      <div className="relative flex max-h-[min(90vh,880px)] w-full max-w-5xl flex-col rounded-xl border border-border bg-background shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold tracking-tight">{t('stock_photos_title')}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">{t('stock_photos_subtitle')}</p>
          </div>
          <button
            type="button"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label={t('stock_photos_close')}
            disabled={applyingPhotoId !== null}
            onClick={() => onOpenChange(false)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <div className="flex flex-wrap gap-1">
            {chipQueries.map((query) => (
              <button
                key={query}
                type="button"
                disabled={rateLimited}
                className={`rounded px-2.5 py-1 text-xs transition-colors ${
                  activeQuery === query && !usingTypedSearch
                    ? 'bg-primary/15 text-primary'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground'
                }`}
                onClick={() => handleChipClick(query)}
              >
                {chipLabel(query)}
              </button>
            ))}
          </div>
          <div className="flex min-w-[200px] flex-1 items-center gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                value={searchText}
                disabled={rateLimited}
                placeholder={t('stock_photos_search_placeholder')}
                className="w-full rounded border border-border bg-muted/40 py-1.5 pl-8 pr-2 text-xs outline-none focus:border-primary/60"
                onChange={(e) => handleSearchInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleSearchSubmit()
                  }
                }}
              />
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {rateLimited ? (
            <p className="mb-3 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
              {t('stock_photos_rate_limited').replace('{seconds}', String(rateLimitSecondsLeft))}
            </p>
          ) : null}
          {applyError ? (
            <p className="mb-3 rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {applyError}
            </p>
          ) : null}
          {loadStatus === 'loading' && <SearchSkeleton />}
          {loadStatus === 'error' && !rateLimited && (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <p className="text-sm text-muted-foreground">{t('stock_photos_load_error')}</p>
              <Button type="button" size="sm" variant="outline" onClick={() => resetAndSearch(activeQuery)}>
                {t('stock_photos_retry')}
              </Button>
            </div>
          )}
          {isEmpty && (
            <p className="py-12 text-center text-sm text-muted-foreground">{t('stock_photos_empty')}</p>
          )}
          {photos.length > 0 && loadStatus !== 'loading' && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {photos.map((photo) => (
                  <PhotoCard
                    key={photo.id}
                    photo={photo}
                    applying={applyingPhotoId === photo.id}
                    onSelect={handleSelect}
                  />
                ))}
              </div>
              {loadStatus === 'loadingMore' && <LoadMoreSkeleton />}
            </>
          )}
        </div>

        {hasMore && loadStatus !== 'loading' && loadStatus !== 'error' && (
          <div className="border-t border-border px-4 py-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full"
              disabled={loadStatus === 'loadingMore' || applyingPhotoId !== null || rateLimited}
              onClick={handleLoadMore}
            >
              {loadStatus === 'loadingMore' ? t('stock_photos_loading_more') : t('stock_photos_load_more')}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
