import { Loader2, Search, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useT } from '@/lib/i18n'
import {
  PEXELS_PER_PAGE,
  fetchPexelsVideoSearch,
  pexelsOrientationFromDimensions,
  pexelsVideoPreviewUrl,
  type PexelsVideo,
} from '@/lib/pexelsApi'
import { applyStockVideoToProject } from '@/lib/pexelsVideoApply'
import { ingestStockVideoForParam } from '@/lib/stockParamApply'
import { isPexelsRateLimited, pexelsRateLimitCooldownMs } from '@/lib/pexelsErrors'
import { formatStockApplyError, notifyStockApplyFailure } from '@/lib/stockApplyErrors'
import { FALLBACK_PEXELS_DEFAULT_VIDEO_QUERIES } from '@/lib/serverConfig'
import { useStockPickerStore } from '@/store/stockPickerStore'
import { useProjectStore } from '@/store/projectStore'

const SEARCH_MIN_CHARS = 5
const SEARCH_DEBOUNCE_MS = 400

function chipLabel(query: string): string {
  if (!query) return query
  return query.charAt(0).toUpperCase() + query.slice(1)
}

function VideoCardSkeleton() {
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="aspect-video bg-muted animate-pulse" />
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
        <VideoCardSkeleton key={i} />
      ))}
    </div>
  )
}

function LoadMoreSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 mt-3">
      {Array.from({ length: 6 }, (_, i) => (
        <VideoCardSkeleton key={i} />
      ))}
    </div>
  )
}

function VideoCard({
  video,
  applying,
  onSelect,
}: {
  video: PexelsVideo
  applying: boolean
  onSelect: (video: PexelsVideo) => void
}) {
  const previewUrl = useMemo(() => pexelsVideoPreviewUrl(video), [video])
  const videoRef = useRef<HTMLVideoElement>(null)
  const [hovering, setHovering] = useState(false)

  const stopPreview = useCallback(() => {
    setHovering(false)
    const el = videoRef.current
    if (!el) return
    el.pause()
    el.removeAttribute('src')
    el.load()
  }, [])

  const startPreview = useCallback(() => {
    if (!previewUrl || applying) return
    setHovering(true)
    const el = videoRef.current
    if (!el) return
    if (el.src !== previewUrl) el.src = previewUrl
    void el.play().catch(() => {
      stopPreview()
    })
  }, [applying, previewUrl, stopPreview])

  useEffect(() => {
    if (!applying) return
    stopPreview()
  }, [applying, stopPreview])

  return (
    <button
      type="button"
      disabled={applying}
      className="group rounded-lg border border-border overflow-hidden text-left transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-60"
      onClick={() => onSelect(video)}
      onMouseEnter={startPreview}
      onMouseLeave={stopPreview}
    >
      <div className="relative aspect-video bg-muted overflow-hidden">
        {video.image ? (
          <img
            src={video.image}
            alt=""
            className={`h-full w-full object-cover transition-opacity duration-150 ${
              hovering && previewUrl ? 'opacity-0' : 'opacity-100'
            }`}
          />
        ) : null}
        {previewUrl ? (
          <video
            ref={videoRef}
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-150 ${
              hovering ? 'opacity-100' : 'opacity-0'
            }`}
            muted
            playsInline
            loop
            preload="none"
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
          href={video.user.url}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-foreground hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {video.user.name}
        </a>
        {' · '}
        <a
          href={video.url}
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

export function StockVideosModal() {
  const t = useT()
  const open = useStockPickerStore((s) => s.videosOpen)
  const videoContext = useStockPickerStore((s) => s.videoContext)
  const closeVideos = useStockPickerStore((s) => s.closeVideos)
  const onOpenChange = useCallback(
    (next: boolean) => {
      if (!next) closeVideos()
    },
    [closeVideos],
  )
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const meta = useProjectStore((s) => s.meta)
  const serverConfig = useProjectStore((s) => s.serverConfig)

  const chipQueries = useMemo(
    () =>
      serverConfig.pexelsDefaultVideoQueries.length > 0
        ? serverConfig.pexelsDefaultVideoQueries
        : [...FALLBACK_PEXELS_DEFAULT_VIDEO_QUERIES],
    [serverConfig.pexelsDefaultVideoQueries],
  )
  const defaultQuery = chipQueries[0] ?? FALLBACK_PEXELS_DEFAULT_VIDEO_QUERIES[0]

  const [searchText, setSearchText] = useState('')
  const [activeQuery, setActiveQuery] = useState<string>(defaultQuery)
  const [videos, setVideos] = useState<PexelsVideo[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loadStatus, setLoadStatus] = useState<'idle' | 'loading' | 'loadingMore' | 'ready' | 'error'>('idle')
  const [applyingVideoId, setApplyingVideoId] = useState<number | null>(null)
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
        const data = await fetchPexelsVideoSearch(query, orientation, pageNum)
        if (seq !== searchSeqRef.current) return
        setVideos((prev) => (mode === 'append' ? [...prev, ...data.videos] : data.videos))
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
            t('stock_videos_rate_limited').replace(
              '{seconds}',
              String(Math.ceil(cooldownMs / 1000)),
            ),
          )
          if (mode === 'append') {
            setLoadStatus('ready')
          } else {
            setVideos([])
            setLoadStatus('error')
          }
          return
        }
        if (mode === 'append') {
          setLoadStatus('ready')
        } else {
          setVideos([])
          setLoadStatus('error')
        }
        appendEventLog(
          'error',
          err instanceof Error ? err.message : t('stock_videos_load_error'),
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
      setApplyingVideoId(null)
      setApplyError(null)
      setSearchText('')
      setActiveQuery(defaultQuery)
      setVideos([])
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
      if (e.key === 'Escape' && applyingVideoId === null) {
        onOpenChange(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [applyingVideoId, onOpenChange, open])

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
    async (video: PexelsVideo) => {
      setApplyError(null)
      setApplyingVideoId(video.id)
      try {
        if (videoContext.mode === 'param') {
          const result = await ingestStockVideoForParam(
            video,
            videoContext.target.uploadContext,
            videoContext.target.field,
          )
          if (!result.ok) {
            reportApplyFailure({ kind: 'video', code: 'apply_failed', message: result.message })
            return
          }
          videoContext.target.onApply(result.result)
          closeVideos()
          return
        }
        const result = await applyStockVideoToProject(video)
        if (!result.ok) {
          reportApplyFailure(
            result.code === 'timeline_full'
              ? { kind: 'video', code: 'timeline_full' }
              : { kind: 'video', code: 'apply_failed', message: result.message },
          )
          return
        }
        closeVideos()
      } catch (err) {
        reportApplyFailure({
          kind: 'video',
          code: 'apply_failed',
          message: err instanceof Error ? err.message : t('stock_videos_apply_error'),
        })
      } finally {
        setApplyingVideoId(null)
      }
    },
    [closeVideos, reportApplyFailure, t, videoContext],
  )

  if (!open) return null

  const isEmpty = loadStatus === 'ready' && videos.length === 0
  const usingTypedSearch = searchText.trim().length >= SEARCH_MIN_CHARS

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/50 supports-backdrop-filter:backdrop-blur-sm"
        aria-label={t('stock_videos_close')}
        onClick={() => {
          if (applyingVideoId === null) onOpenChange(false)
        }}
      />
      <div className="relative flex max-h-[min(90vh,880px)] w-full max-w-5xl flex-col rounded-xl border border-border bg-background shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold tracking-tight">{t('stock_videos_title')}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">{t('stock_videos_subtitle')}</p>
          </div>
          <button
            type="button"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label={t('stock_videos_close')}
            disabled={applyingVideoId !== null}
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
                placeholder={t('stock_videos_search_placeholder')}
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
              {t('stock_videos_rate_limited').replace('{seconds}', String(rateLimitSecondsLeft))}
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
              <p className="text-sm text-muted-foreground">{t('stock_videos_load_error')}</p>
              <Button type="button" size="sm" variant="outline" onClick={() => resetAndSearch(activeQuery)}>
                {t('stock_videos_retry')}
              </Button>
            </div>
          )}
          {isEmpty && (
            <p className="py-12 text-center text-sm text-muted-foreground">{t('stock_videos_empty')}</p>
          )}
          {videos.length > 0 && loadStatus !== 'loading' && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {videos.map((video) => (
                  <VideoCard
                    key={video.id}
                    video={video}
                    applying={applyingVideoId === video.id}
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
              disabled={loadStatus === 'loadingMore' || applyingVideoId !== null || rateLimited}
              onClick={handleLoadMore}
            >
              {loadStatus === 'loadingMore' ? t('stock_videos_loading_more') : t('stock_videos_load_more')}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
