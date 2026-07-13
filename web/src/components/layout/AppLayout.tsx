import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '@/lib/apiClient'
import { parseComposeHealth, type HealthPayload } from '@/lib/composeHealth'
import {
  markApiConnected,
  markApiDisconnected,
  registerApiHealthProbe,
} from '@/lib/apiConnection'
import { syncBrokenClipDiagnostics } from '@/lib/brokenClips'
import {
  prefetchProjectClipDetails,
  syncInvalidParamsDiagnostics,
} from '@/lib/invalidClipParams'
import { stopPlaybackOnApiLoss } from '@/lib/playbackOnApiLoss'
import { useT } from '@/lib/i18n'
import { useProjectStore, projectRedo, projectUndo } from '@/store/projectStore'
import { AppMenuBar } from './AppMenuBar'
import { StockPickerHost } from './StockPickerHost'
import { EventLogPanel } from './EventLogPanel'
import { JobsView } from './JobsView'
import { LeftPanel } from './LeftPanel'
import { PreviewPane } from './PreviewPane'
import { PluginCatalogPane } from './PluginCatalogPane'
import { ComposePanel } from './ComposePanel'
import { PropertiesPane } from './PropertiesPane'
import { SettingsPanel } from './SettingsPanel'
import { TimelinePane } from './TimelinePane'
import { ToastStack } from '@/components/ui/toast-stack'
import { useAudioAnalysisCoordinator } from '@/hooks/useAudioAnalysisCoordinator'

/**
 * 4-panel layout:
 *
 *  ┌──────────┬─────────────────────┬────────────────┐
 *  │  Left    │  Preview            │  Properties    │
 *  │  Panel   │                     │  Panel         │
 *  │          ├─────────────────────┤                │
 *  │          │  Timeline           │                │
 *  └──────────┴─────────────────────┴────────────────┘
 */
export function AppLayout() {
  const t = useT()
  const themeMode = useProjectStore((s) => s.themeMode)
  const layoutPrefs = useProjectStore((s) => s.appLayoutPrefs)
  const setLayoutPrefs = useProjectStore((s) => s.setLayoutPrefs)
  const showLogsPanel = useProjectStore((s) => s.showLogsPanel)
  const showSettingsPanel = useProjectStore((s) => s.showSettingsPanel)
  const appView = useProjectStore((s) => s.appView)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const apiRetryInSeconds = useProjectStore((s) => s.apiRetryInSeconds)
  const requestApiRetryNow = useProjectStore((s) => s.requestApiRetryNow)
  const setApiConnectionStatus = useProjectStore((s) => s.setApiConnectionStatus)
  const setApiRetryInSeconds = useProjectStore((s) => s.setApiRetryInSeconds)
  const setComposeHealth = useProjectStore((s) => s.setComposeHealth)
  const setPexelsAvailable = useProjectStore((s) => s.setPexelsAvailable)
  const setFfmpegAvailable = useProjectStore((s) => s.setFfmpegAvailable)
  const apiRetryNonce = useProjectStore((s) => s.apiRetryNonce)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const selection = useProjectStore((s) => s.selection)
  const pluginPicker = useProjectStore((s) => s.pluginPicker)
  const composePanelOpen = useProjectStore((s) => s.composePanelOpen)
  const appSettings = useProjectStore((s) => s.appSettings)
  const fetchCatalog = useProjectStore((s) => s.fetchCatalog)
  const fetchFontCatalog = useProjectStore((s) => s.fetchFontCatalog)
  const fetchThemePresets = useProjectStore((s) => s.fetchThemePresets)
  const fetchServerConfig = useProjectStore((s) => s.fetchServerConfig)
  const tracks = useProjectStore((s) => s.tracks)
  const projectSettings = useProjectStore((s) => s.projectSettings)
  const catalogLoadStatus = useProjectStore((s) => s.catalogLoadStatus)
  const catalogClips = useProjectStore((s) => s.catalogClips)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  useAudioAnalysisCoordinator()
  const containerRef = useRef<HTMLDivElement>(null)
  const isDraggingPreview = useRef(false)
  const isDraggingLeft = useRef(false)
  const isDraggingRight = useRef(false)
  const prevSelectionRef = useRef(selection)
  const prevApiStatusRef = useRef(apiConnectionStatus)

  // Global undo/redo — same behavior as Edit menu; skip when typing in inputs.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return

      const mod = e.metaKey || e.ctrlKey
      if (mod && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        const { pastStates } = useProjectStore.temporal.getState()
        if (pastStates.length === 0) return
        e.preventDefault()
        projectUndo()
        return
      }
      if (mod && e.key.toLowerCase() === 'z' && e.shiftKey) {
        const { futureStates } = useProjectStore.temporal.getState()
        if (futureStates.length === 0) return
        e.preventDefault()
        projectRedo()
        return
      }
      // Windows-style redo
      if (e.ctrlKey && !e.metaKey && e.key.toLowerCase() === 'y') {
        const { futureStates } = useProjectStore.temporal.getState()
        if (futureStates.length === 0) return
        e.preventDefault()
        projectRedo()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // Auto-open right panel when user selects something for the first time
  useEffect(() => {
    const prev = prevSelectionRef.current
    prevSelectionRef.current = selection
    if (!prev && selection) {
      setLayoutPrefs({ rightCollapsed: false })
    }
  }, [selection, setLayoutPrefs])

  useEffect(() => {
    if (pluginPicker) {
      setLayoutPrefs({ rightCollapsed: false })
    }
  }, [pluginPicker, setLayoutPrefs])

  useEffect(() => {
    if (composePanelOpen) {
      setLayoutPrefs({ rightCollapsed: false })
    }
  }, [composePanelOpen, setLayoutPrefs])

  useEffect(() => {
    if (apiConnectionStatus !== 'connected') return
    void fetchServerConfig()
    void fetchCatalog()
    void fetchFontCatalog()
    void fetchThemePresets()
  }, [
    apiConnectionStatus,
    appSettings.locale,
    fetchCatalog,
    fetchFontCatalog,
    fetchServerConfig,
    fetchThemePresets,
  ])

  useEffect(() => {
    syncBrokenClipDiagnostics(
      { tracks, projectSettings, catalogLoadStatus, catalogClips },
      appendEventLog,
    )
  }, [tracks, projectSettings, catalogLoadStatus, catalogClips, appendEventLog])

  useEffect(() => {
    if (catalogLoadStatus !== 'ready') return
    prefetchProjectClipDetails()
  }, [catalogLoadStatus, tracks, projectSettings, appSettings.locale])

  useEffect(() => {
    syncInvalidParamsDiagnostics(
      {
        tracks,
        projectSettings,
        catalogLoadStatus,
        catalogClips,
        catalogDetailCache,
        locale: appSettings.locale,
      },
      appendEventLog,
    )
  }, [
    tracks,
    projectSettings,
    catalogLoadStatus,
    catalogClips,
    catalogDetailCache,
    appSettings.locale,
    appendEventLog,
  ])

  useEffect(() => {
    const prev = prevApiStatusRef.current
    prevApiStatusRef.current = apiConnectionStatus
    if (prev === 'connected' && apiConnectionStatus === 'disconnected') {
      stopPlaybackOnApiLoss()
    }
  }, [apiConnectionStatus])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const target = e.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return
      const state = useProjectStore.getState()
      if (state.composePanelOpen) {
        state.closeComposePanel()
        return
      }
      if (state.pluginPicker) {
        state.closePluginPicker()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const [systemTheme, setSystemTheme] = useState<'dark' | 'light'>(() => {
    if (typeof window === 'undefined') return 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e: MediaQueryListEvent) => setSystemTheme(e.matches ? 'dark' : 'light')
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    let disposed = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    let countdownTimer: ReturnType<typeof setInterval> | null = null
    let backoffSeconds = 1
    let nextRetryAt = 0

    const clearTimers = () => {
      if (retryTimer) clearTimeout(retryTimer)
      if (countdownTimer) clearInterval(countdownTimer)
      retryTimer = null
      countdownTimer = null
    }

    const beginCountdown = (seconds: number) => {
      nextRetryAt = Date.now() + seconds * 1000
      setApiRetryInSeconds(seconds)
      if (countdownTimer) clearInterval(countdownTimer)
      countdownTimer = setInterval(() => {
        const remaining = Math.max(0, Math.ceil((nextRetryAt - Date.now()) / 1000))
        setApiRetryInSeconds(remaining)
      }, 250)
    }

    const scheduleRetry = () => {
      beginCountdown(backoffSeconds)
      retryTimer = setTimeout(() => {
        void checkHealth()
      }, backoffSeconds * 1000)
      backoffSeconds = Math.min(20, backoffSeconds < 2 ? 2 : backoffSeconds * 2)
    }

    const checkHealth = async () => {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5000)
      try {
        const res = await apiFetch('/health', {
          cache: 'no-store',
          signal: controller.signal,
        })
        if (!res.ok) throw new Error(`health ${res.status}`)
        if (disposed) return
        clearTimers()
        setApiConnectionStatus('connected')
        setApiRetryInSeconds(null)
        backoffSeconds = 1
        const data = await res.json() as HealthPayload
        markApiConnected()
        setComposeHealth(parseComposeHealth(data))
        setPexelsAvailable(data.pexels_available === true)
        setFfmpegAvailable(data.ffmpeg === true)
        if (data.ffmpeg === false) {
          appendEventLog('warn', t('event_ffmpeg_missing'))
        }
        if (data.gl?.available === false) {
          appendEventLog('warn', t('event_gl_unavailable'))
        }
        retryTimer = setTimeout(() => void checkHealth(), 4000)
      } catch {
        if (disposed) return
        clearTimers()
        setApiConnectionStatus('disconnected')
        setComposeHealth(null)
        setPexelsAvailable(null)
        setFfmpegAvailable(null)
        markApiDisconnected()
        scheduleRetry()
      } finally {
        clearTimeout(timeout)
      }
    }
    setApiConnectionStatus('checking')
    setApiRetryInSeconds(null)
    const unregisterProbe = registerApiHealthProbe(() => {
      clearTimers()
      void checkHealth()
    })
    void checkHealth()
    return () => {
      disposed = true
      clearTimers()
      unregisterProbe()
    }
  }, [apiRetryNonce, appendEventLog, setApiConnectionStatus, setApiRetryInSeconds, setComposeHealth, setFfmpegAvailable, setPexelsAvailable, t])

  const activeTheme = themeMode === 'system' ? systemTheme : themeMode

  const onPreviewDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDraggingPreview.current = true
    const startY = e.clientY
    const startPct = layoutPrefs.previewHeightPct
    const rootRect = containerRef.current?.getBoundingClientRect()
    if (!rootRect || rootRect.height < 1) return

    const onMove = (me: MouseEvent) => {
      if (!isDraggingPreview.current) return
      const h = containerRef.current?.getBoundingClientRect().height ?? rootRect.height
      if (h < 1) return
      const deltaPct = ((me.clientY - startY) / h) * 100
      setLayoutPrefs({ previewHeightPct: startPct + deltaPct })
    }
    const onUp = () => {
      isDraggingPreview.current = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [layoutPrefs.previewHeightPct, setLayoutPrefs])

  const onLeftDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDraggingLeft.current = true
    const startX = e.clientX
    const startPct = layoutPrefs.leftWidthPct
    const rootRect = containerRef.current?.getBoundingClientRect()
    if (!rootRect || rootRect.width < 1) return

    const onMove = (me: MouseEvent) => {
      if (!isDraggingLeft.current) return
      const w = containerRef.current?.getBoundingClientRect().width ?? rootRect.width
      if (w < 1) return
      const deltaPct = ((me.clientX - startX) / w) * 100
      setLayoutPrefs({ leftWidthPct: startPct + deltaPct })
    }
    const onUp = () => {
      isDraggingLeft.current = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [layoutPrefs.leftWidthPct, setLayoutPrefs])

  const onRightDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDraggingRight.current = true
    const startX = e.clientX
    const startPct = layoutPrefs.rightWidthPct
    const rootRect = containerRef.current?.getBoundingClientRect()
    if (!rootRect || rootRect.width < 1) return

    const onMove = (me: MouseEvent) => {
      if (!isDraggingRight.current) return
      const w = containerRef.current?.getBoundingClientRect().width ?? rootRect.width
      if (w < 1) return
      const deltaPct = ((startX - me.clientX) / w) * 100
      setLayoutPrefs({ rightWidthPct: startPct + deltaPct })
    }
    const onUp = () => {
      isDraggingRight.current = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [layoutPrefs.rightWidthPct, setLayoutPrefs])

  return (
    <div
      className={`${activeTheme} flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground`}
    >
      <AppMenuBar />
      <StockPickerHost />
      {apiConnectionStatus !== 'connected' && (
        <div className="shrink-0 border-b border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          <div className="flex items-center justify-between gap-2">
            <span>
              {t('layout_api_disconnected')}
              {' '}
              {apiRetryInSeconds != null
                ? t('layout_api_retry_countdown').replace('{n}', String(apiRetryInSeconds))
                : t('layout_api_retrying')}
            </span>
            <button
              type="button"
              className="rounded border border-destructive/40 px-2 py-0.5 text-[11px] hover:bg-destructive/15"
              onClick={requestApiRetryNow}
            >
              {t('api_retry_now')}
            </button>
          </div>
        </div>
      )}
      <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
        {appView === 'jobs' ? (
          <JobsView />
        ) : (
        <>
        <div
          ref={containerRef}
          className="flex flex-1 min-h-0 overflow-hidden"
        >
          {/* Left panel: project settings + plugin browser */}
          <aside
            className="shrink-0 flex flex-col border-r border-border overflow-hidden"
            style={{ width: layoutPrefs.leftCollapsed ? 0 : `${layoutPrefs.leftWidthPct}%` }}
          >
            <div className="flex h-8 items-center justify-end border-b border-border px-2">
              <button
                type="button"
                className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                onClick={() => setLayoutPrefs({ leftCollapsed: !layoutPrefs.leftCollapsed })}
                aria-label={layoutPrefs.leftCollapsed ? t('layout_expand_left') : t('layout_collapse_left')}
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
            <LeftPanel />
          </aside>
          {!layoutPrefs.leftCollapsed && (
            <div
              className="w-1 cursor-col-resize bg-border hover:bg-primary/50 shrink-0 transition-colors"
              onMouseDown={onLeftDividerMouseDown}
            />
          )}
          {layoutPrefs.leftCollapsed && (
            <button
              type="button"
              className="m-1 h-7 w-7 shrink-0 rounded border border-border text-muted-foreground hover:bg-accent hover:text-foreground"
              onClick={() => setLayoutPrefs({ leftCollapsed: false })}
              aria-label={t('layout_expand_left')}
            >
              <ChevronRight className="mx-auto h-4 w-4" />
            </button>
          )}

          {/* Center column: preview + resize handle + timeline */}
          <div className="flex flex-col flex-1 overflow-hidden">
            <div
              className="overflow-hidden border-b border-border"
              style={{ flexBasis: `${layoutPrefs.previewHeightPct}%`, minHeight: 84 }}
            >
              <PreviewPane />
            </div>

            {/* Horizontal resize handle */}
            <div
              className="h-1 cursor-row-resize bg-border hover:bg-primary/50 shrink-0 transition-colors"
              onMouseDown={onPreviewDividerMouseDown}
            />

            <div className="min-h-[120px] flex-1 overflow-hidden">
              <TimelinePane />
            </div>
          </div>

          {!layoutPrefs.rightCollapsed && (
            <div
              className="w-1 cursor-col-resize bg-border hover:bg-primary/50 shrink-0 transition-colors"
              onMouseDown={onRightDividerMouseDown}
            />
          )}
          {/* Right panel: properties */}
          <aside
            className="shrink-0 flex flex-col border-l border-border overflow-hidden"
            style={{ width: layoutPrefs.rightCollapsed ? 0 : `${layoutPrefs.rightWidthPct}%` }}
          >
            <div className="flex h-8 items-center justify-start border-b border-border px-2">
              <button
                type="button"
                className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                onClick={() => setLayoutPrefs({ rightCollapsed: !layoutPrefs.rightCollapsed })}
                aria-label={layoutPrefs.rightCollapsed ? t('layout_expand_right') : t('layout_collapse_right')}
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              {composePanelOpen ? (
                <ComposePanel />
              ) : pluginPicker ? (
                <PluginCatalogPane />
              ) : (
                <PropertiesPane />
              )}
            </div>
          </aside>
          {layoutPrefs.rightCollapsed && (
            <button
              type="button"
              className="m-1 h-7 w-7 shrink-0 rounded border border-border text-muted-foreground hover:bg-accent hover:text-foreground"
              onClick={() => setLayoutPrefs({ rightCollapsed: false })}
              aria-label={t('layout_expand_right')}
            >
              <ChevronLeft className="mx-auto h-4 w-4" />
            </button>
          )}
          {showSettingsPanel && <SettingsPanel />}
        </div>
        {showLogsPanel && (
          <div className="h-40 shrink-0 border-t border-border">
            <EventLogPanel />
          </div>
        )}
        </>
        )}
      </div>
      <ToastStack />
    </div>
  )
}
