import { ArrowLeft, ChevronDown, Download, Play, Trash2, XCircle } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  cancelJob,
  fetchJobDiscordVideoBlob,
  fetchJobVideoBlob,
  type DiscordExportMaxMb,
  getJob,
  hydrateActiveJobs,
  isJobActive,
  isJobTerminal,
  jobProgressWebSocketUrl,
  listJobs,
  mergeJobProgress,
  removeJobArtifacts,
  type JobRecord,
  type JobStatus,
} from '@/lib/jobsClient'
import { useT } from '@/lib/i18n'
import { useProjectStore } from '@/store/projectStore'
import { useToastStore } from '@/store/toastStore'

const STATUS_KEYS: Record<JobStatus, 'jobs_status_queued' | 'jobs_status_preparing' | 'jobs_status_rendering' | 'jobs_status_done' | 'jobs_status_cancelled' | 'jobs_status_failed' | 'jobs_status_interrupted'> = {
  queued: 'jobs_status_queued',
  preparing: 'jobs_status_preparing',
  rendering: 'jobs_status_rendering',
  done: 'jobs_status_done',
  cancelled: 'jobs_status_cancelled',
  failed: 'jobs_status_failed',
  interrupted: 'jobs_status_interrupted',
}

function formatMs(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  const sec = ms / 1000
  if (sec < 60) return `${sec.toFixed(1)} s`
  const min = Math.floor(sec / 60)
  const rem = Math.round(sec % 60)
  return `${min}m ${rem}s`
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

type RenderParallelism = 'single' | 'multi'

function renderParallelismModeLabel(mode: RenderParallelism, t: ReturnType<typeof useT>): string {
  return mode === 'multi'
    ? t('settings_render_parallelism_multi')
    : t('settings_render_parallelism_single')
}

function formatRenderParallelism(
  requested: RenderParallelism | null,
  effective: RenderParallelism | null,
  t: ReturnType<typeof useT>,
): string {
  if (!effective) return '—'
  const effectiveLabel = renderParallelismModeLabel(effective, t)
  if (!requested || requested === effective) return effectiveLabel
  return t('jobs_render_parallelism_mismatch')
    .replace('{effective}', effectiveLabel)
    .replace('{requested}', renderParallelismModeLabel(requested, t))
}

function statusBadgeClass(status: JobStatus): string {
  switch (status) {
    case 'done':
      return 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
    case 'rendering':
    case 'preparing':
      return 'bg-sky-500/15 text-sky-700 dark:text-sky-400'
    case 'queued':
      return 'bg-amber-500/15 text-amber-800 dark:text-amber-300'
    case 'cancelled':
      return 'bg-muted text-muted-foreground'
    case 'failed':
    case 'interrupted':
      return 'bg-destructive/15 text-destructive'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

export function JobsView() {
  const t = useT()
  const focusedJobId = useProjectStore((s) => s.focusedJobId)
  const setFocusedJobId = useProjectStore((s) => s.setFocusedJobId)
  const backToEditor = useProjectStore((s) => s.backToEditor)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const ffmpegAvailable = useProjectStore((s) => s.ffmpegAvailable)

  const [jobs, setJobs] = useState<JobRecord[]>([])
  const [selected, setSelected] = useState<JobRecord | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [busyLabel, setBusyLabel] = useState<string | null>(null)
  const [removeOpen, setRemoveOpen] = useState(false)
  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const videoUrlRef = useRef<string | null>(null)

  const pickSelected = useCallback(
    (rows: JobRecord[], prev: JobRecord | null): JobRecord | null => {
      const targetId = focusedJobId ?? prev?.id
      if (targetId) {
        const match = rows.find((row) => row.id === targetId)
        if (!match) return prev
        if (prev?.id === match.id) return mergeJobProgress(prev, match)
        return match
      }
      if (prev) {
        const updated = rows.find((row) => row.id === prev.id)
        if (updated) {
          return prev.id === updated.id ? mergeJobProgress(prev, updated) : updated
        }
      }
      const active = rows.find((row) => isJobActive(row.status))
      return active ?? rows[0] ?? null
    },
    [focusedJobId],
  )

  const refreshList = useCallback(async () => {
    if (apiConnectionStatus !== 'connected') return
    try {
      const rows = await hydrateActiveJobs(await listJobs())
      setJobs(rows)
      setLoadError(null)
      setSelected((prev) => pickSelected(rows, prev))
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : t('jobs_list_load_failed'))
    }
  }, [apiConnectionStatus, pickSelected, t])

  useEffect(() => {
    void refreshList()
    const timer = window.setInterval(() => void refreshList(), 4000)
    return () => window.clearInterval(timer)
  }, [refreshList])

  useEffect(() => {
    if (!focusedJobId || jobs.length === 0) return
    setSelected((prev) => {
      if (prev?.id === focusedJobId) return prev
      return jobs.find((row) => row.id === focusedJobId) ?? prev
    })
  }, [focusedJobId, jobs])

  const activeJobId = selected && isJobActive(selected.status) ? selected.id : null

  useEffect(() => {
    if (!activeJobId) return

    const ws = new WebSocket(jobProgressWebSocketUrl(activeJobId))
    ws.onmessage = (event) => {
      try {
        const record = JSON.parse(String(event.data)) as JobRecord
        setSelected((prev) => (prev?.id === record.id ? mergeJobProgress(prev, record) : record))
        setJobs((prev) =>
          prev.map((row) => (row.id === record.id ? mergeJobProgress(row, record) : row)),
        )
      } catch {
        /* ignore malformed */
      }
    }
    ws.onerror = () => {
      ws.close()
    }
    return () => ws.close()
  }, [activeJobId])

  useEffect(() => {
    return () => {
      if (videoUrlRef.current) {
        URL.revokeObjectURL(videoUrlRef.current)
        videoUrlRef.current = null
      }
    }
  }, [])

  const handleSelect = (row: JobRecord) => {
    setSelected(row)
    setFocusedJobId(row.id)
  }

  const handleCancel = async () => {
    if (!selected) return
    setBusy(true)
    try {
      await cancelJob(selected.id)
      const fresh = await getJob(selected.id)
      setSelected(fresh)
      await refreshList()
    } catch (err) {
      appendEventLog('error', err instanceof Error ? err.message : t('jobs_submit_failed'))
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async () => {
    if (!selected) return
    setBusy(true)
    try {
      await removeJobArtifacts(selected.id)
      setRemoveOpen(false)
      setSelected(null)
      setFocusedJobId(null)
      await refreshList()
    } catch (err) {
      appendEventLog('error', err instanceof Error ? err.message : t('jobs_submit_failed'))
    } finally {
      setBusy(false)
    }
  }

  const handleDownload = async () => {
    if (!selected) return
    setBusy(true)
    setBusyLabel(null)
    try {
      const blob = await fetchJobVideoBlob(selected.id, 'attachment')
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${selected.title || selected.id}.mp4`.replace(/[/\\?%*:|"<>]/g, '-')
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      appendEventLog('error', err instanceof Error ? err.message : t('jobs_submit_failed'))
    } finally {
      setBusy(false)
      setBusyLabel(null)
    }
  }

  const handleDownloadDiscord = async (maxMb: DiscordExportMaxMb) => {
    if (!selected) return
    setBusy(true)
    setBusyLabel(t('jobs_preparing_discord_export').replace('{maxMb}', String(maxMb)))
    try {
      const blob = await fetchJobDiscordVideoBlob(selected.id, maxMb)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      const suffix = maxMb === 8 ? '-discord.mp4' : `-discord-${maxMb}mb.mp4`
      anchor.download = `${selected.title || selected.id}${suffix}`.replace(/[/\\?%*:|"<>]/g, '-')
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      const message = err instanceof Error ? err.message : t('jobs_discord_export_failed')
      appendEventLog('error', message)
      if (!useProjectStore.getState().showLogsPanel) {
        useToastStore.getState().pushToast(message, 'error')
      }
    } finally {
      setBusy(false)
      setBusyLabel(null)
    }
  }

  const handlePlay = async () => {
    if (!selected) return
    setBusy(true)
    try {
      if (videoUrlRef.current) {
        URL.revokeObjectURL(videoUrlRef.current)
        videoUrlRef.current = null
      }
      const blob = await fetchJobVideoBlob(selected.id, 'inline')
      const url = URL.createObjectURL(blob)
      videoUrlRef.current = url
      setVideoUrl(url)
    } catch (err) {
      appendEventLog('error', err instanceof Error ? err.message : t('jobs_submit_failed'))
    } finally {
      setBusy(false)
    }
  }

  const closeVideo = () => {
    if (videoUrlRef.current) {
      URL.revokeObjectURL(videoUrlRef.current)
      videoUrlRef.current = null
    }
    setVideoUrl(null)
  }

  const canCancel = selected != null && isJobActive(selected.status)
  const canRemove =
    selected != null &&
    (isJobTerminal(selected.status) || selected.status === 'queued')
  const canPlayOrDownload = selected?.status === 'done'
  const canDownloadDiscord = canPlayOrDownload && ffmpegAvailable === true

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2 shrink-0">
        <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={backToEditor}>
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('jobs_back_to_project')}
        </Button>
        <h1 className="text-sm font-semibold">{t('jobs_title')}</h1>
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div className="w-[min(360px,40%)] shrink-0 overflow-y-auto border-r border-border">
          {loadError && (
            <p className="px-3 py-2 text-xs text-destructive">{loadError}</p>
          )}
          {jobs.length === 0 && !loadError ? (
            <p className="px-3 py-6 text-xs text-muted-foreground">{t('jobs_empty')}</p>
          ) : (
            <ul className="divide-y divide-border">
              {jobs.map((row) => {
                const active = selected?.id === row.id
                return (
                  <li key={row.id}>
                    <button
                      type="button"
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-accent/60 ${
                        active ? 'bg-accent/40' : ''
                      }`}
                      onClick={() => handleSelect(row)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-medium truncate">{row.title || row.id}</span>
                        <span
                          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${statusBadgeClass(row.status)}`}
                        >
                          {t(STATUS_KEYS[row.status])}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[10px] text-muted-foreground">
                        {formatDate(row.created_at)}
                      </p>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="flex flex-1 flex-col min-w-0 overflow-y-auto p-4">
          {!selected ? (
            <p className="text-sm text-muted-foreground">{t('jobs_select_hint')}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">{selected.title || selected.id}</h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('jobs_dimensions')
                      .replace('{width}', String(selected.width))
                      .replace('{height}', String(selected.height))
                      .replace('{fps}', String(selected.fps))}
                  </p>
                </div>
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadgeClass(selected.status)}`}
                >
                  {t(STATUS_KEYS[selected.status])}
                </span>
              </div>

              {isJobActive(selected.status) && (
                <div className="mt-4 space-y-1">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>
                      {selected.status === 'queued'
                        ? t('jobs_status_queued')
                        : t('jobs_status_rendering')}
                    </span>
                    <span>
                      {selected.total > 0
                        ? `${Math.round(selected.percent)}%`
                        : '…'}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full bg-primary transition-[width] duration-300"
                      style={{
                        width: `${
                          selected.total > 0
                            ? Math.min(100, Math.max(0, selected.percent))
                            : selected.status === 'queued'
                              ? 0
                              : 8
                        }%`,
                      }}
                    />
                  </div>
                </div>
              )}

              <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">{t('jobs_created')}</dt>
                  <dd>{formatDate(selected.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">{t('jobs_project_duration')}</dt>
                  <dd>{`${selected.duration_s.toFixed(1)} s`}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">{t('jobs_render_duration')}</dt>
                  <dd>{formatMs(selected.render_duration_ms)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">{t('jobs_render_parallelism')}</dt>
                  <dd>
                    {formatRenderParallelism(
                      selected.render_parallelism_requested,
                      selected.render_parallelism_effective,
                      t,
                    )}
                  </dd>
                </div>
              </dl>

              {selected.error && (
                <p className="mt-3 rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {selected.error}
                </p>
              )}

              {busyLabel && (
                <p className="mt-3 text-xs text-muted-foreground">{busyLabel}</p>
              )}

              <div className="mt-4 flex flex-wrap gap-2">
                {canCancel && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1 text-xs"
                    disabled={busy}
                    onClick={() => void handleCancel()}
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    {t('jobs_cancel')}
                  </Button>
                )}
                {canPlayOrDownload && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 gap-1 text-xs"
                      disabled={busy}
                      onClick={() => void handlePlay()}
                    >
                      <Play className="h-3.5 w-3.5" />
                      {t('jobs_play')}
                    </Button>
                    <div className="inline-flex">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 gap-1 rounded-r-none border-r-0 text-xs"
                        disabled={busy}
                        onClick={() => void handleDownload()}
                      >
                        <Download className="h-3.5 w-3.5" />
                        {t('jobs_download')}
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          disabled={busy}
                          className="inline-flex h-8 items-center rounded-r-md border border-input bg-background px-1.5 text-xs hover:bg-muted disabled:pointer-events-none disabled:opacity-50"
                        >
                          <ChevronDown className="h-3.5 w-3.5" />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" side="bottom" sideOffset={4} className="w-52">
                          <DropdownMenuGroup>
                            <DropdownMenuLabel>{t('jobs_download_share')}</DropdownMenuLabel>
                            <DropdownMenuItem
                              disabled={!canDownloadDiscord}
                              onClick={() => void handleDownloadDiscord(8)}
                            >
                              {t('jobs_download_discord_8mb')}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              disabled={!canDownloadDiscord}
                              onClick={() => void handleDownloadDiscord(50)}
                            >
                              {t('jobs_download_discord_50mb')}
                            </DropdownMenuItem>
                          </DropdownMenuGroup>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </>
                )}
                {canRemove && (
                  <Button
                    variant="destructive"
                    size="sm"
                    className="h-8 gap-1 text-xs"
                    disabled={busy}
                    onClick={() => setRemoveOpen(true)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    {t('jobs_remove')}
                  </Button>
                )}
              </div>

              {videoUrl && (
                <div className="mt-4 space-y-2">
                  <div className="flex justify-end">
                    <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={closeVideo}>
                      {t('jobs_close_video')}
                    </Button>
                  </div>
                  <video
                    src={videoUrl}
                    controls
                    className="max-h-[50vh] w-full rounded border border-border bg-black"
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <AlertDialog open={removeOpen} onOpenChange={setRemoveOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('jobs_remove_confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('jobs_remove_confirm_body')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('dialog_cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void handleRemove()}>
              {t('jobs_remove')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
