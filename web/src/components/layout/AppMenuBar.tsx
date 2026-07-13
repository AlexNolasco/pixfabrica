import { Laptop, Moon, Sun } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
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
  Menubar,
  MenubarContent,
  MenubarItem,
  MenubarMenu,
  MenubarRadioGroup,
  MenubarRadioItem,
  MenubarSeparator,
  MenubarShortcut,
  MenubarSub,
  MenubarSubContent,
  MenubarSubTrigger,
  MenubarTrigger,
} from '@/components/ui/menubar'
import {
  AddToGalleryDialog,
  galleryPublishUiEnabled,
} from '@/components/layout/AddToGalleryDialog'
import { ProjectImportConfirmDialog } from '@/components/layout/ProjectImportConfirmDialog'
import { StarterGalleryModal } from '@/components/layout/StarterGalleryModal'
import { useStockPickerStore } from '@/store/stockPickerStore'
import { useT } from '@/lib/i18n'
import {
  projectHasActiveRenderJobs,
  submitCurrentProjectRender,
} from '@/lib/renderJobSubmit'
import { useProjectValidationBlocked } from '@/lib/invalidClipParams'
import {
  executeNewProject,
  executeProjectImport,
  exportProjectBundle,
  exportProjectJson,
  parseProjectBundleImportFile,
  parseProjectImportFile,
  projectHasTimelineContent,
  type ProjectImportPayload,
} from '@/lib/projectFileActions'
import { useProjectStore, projectRedo, projectUndo, type UiLocale } from '@/store/projectStore'
import { useStore } from 'zustand/react'

export function AppMenuBar() {
  const t = useT()
  const importInputRef = useRef<HTMLInputElement>(null)
  const bundleImportInputRef = useRef<HTMLInputElement>(null)
  const [newProjectOpen, setNewProjectOpen] = useState(false)
  const [importConfirmOpen, setImportConfirmOpen] = useState(false)
  const [galleryOpen, setGalleryOpen] = useState(false)
  const [addToGalleryOpen, setAddToGalleryOpen] = useState(false)
  const [pendingImport, setPendingImport] = useState<{
    payload: ProjectImportPayload
    importBundleId?: string | null
    kind: 'json' | 'bundle'
  } | null>(null)
  const [bundleExporting, setBundleExporting] = useState(false)
  const [queueConfirmOpen, setQueueConfirmOpen] = useState(false)
  const [renderSubmitting, setRenderSubmitting] = useState(false)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const themeMode = useProjectStore((s) => s.themeMode)
  const toggleThemeMode = useProjectStore((s) => s.toggleThemeMode)
  const setThemeMode = useProjectStore((s) => s.setThemeMode)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const apiRetryInSeconds = useProjectStore((s) => s.apiRetryInSeconds)
  const showLogsPanel = useProjectStore((s) => s.showLogsPanel)
  const toggleLogsPanel = useProjectStore((s) => s.toggleLogsPanel)
  const setSettingsPanelOpen = useProjectStore((s) => s.setSettingsPanelOpen)
  const openJobsView = useProjectStore((s) => s.openJobsView)
  const appSettings = useProjectStore((s) => s.appSettings)
  const setAppSettings = useProjectStore((s) => s.setAppSettings)
  const pexelsAvailable = useProjectStore((s) => s.pexelsAvailable)
  const openMenuPhotos = useStockPickerStore((s) => s.openMenuPhotos)
  const openMenuVideos = useStockPickerStore((s) => s.openMenuVideos)
  const closeAllStockPickers = useStockPickerStore((s) => s.closeAll)

  const canUndo = useStore(useProjectStore.temporal, (s) => s.pastStates.length > 0)
  const canRedo = useStore(useProjectStore.temporal, (s) => s.futureStates.length > 0)
  const hasTimelineContent = useProjectStore((s) => s.tracks.length > 0 || s.sounds.length > 0)
  const projectValidationBlocked = useProjectValidationBlocked()

  const ThemeIcon = themeMode === 'dark' ? Sun : themeMode === 'light' ? Moon : Laptop
  const themeTitle =
    themeMode === 'dark' ? t('theme_title_dark')
    : themeMode === 'light' ? t('theme_title_light')
    : t('theme_title_system')

  const connectionBadgeClass =
    apiConnectionStatus === 'connected'
      ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
      : apiConnectionStatus === 'disconnected'
        ? 'bg-destructive/15 text-destructive'
        : 'bg-amber-500/15 text-amber-700 dark:text-amber-400'

  const connectionLabel =
    apiConnectionStatus === 'connected'
      ? t('api_connected')
      : apiConnectionStatus === 'disconnected'
        ? `${t('api_disconnected')}${apiRetryInSeconds != null ? ` (${t('api_retry_in')} ${apiRetryInSeconds}s)` : ''}`
        : t('api_checking')

  const apiOffline = apiConnectionStatus !== 'connected'

  useEffect(() => {
    if (!apiOffline) return
    setGalleryOpen(false)
    closeAllStockPickers()
    setImportConfirmOpen(false)
    setPendingImport(null)
  }, [apiOffline, closeAllStockPickers])

  const handleNewProject = () => {
    if (projectHasTimelineContent()) {
      setNewProjectOpen(true)
      return
    }
    executeNewProject()
  }

  const handleNewProjectConfirm = () => {
    executeNewProject()
    setNewProjectOpen(false)
  }

  const handleImportClick = () => {
    if (apiOffline) return
    importInputRef.current?.click()
  }

  const handleImportFile = async (file: File | undefined) => {
    if (apiOffline || !file) return
    const result = await parseProjectImportFile(file)
    if (!result.ok) {
      appendEventLog('warn', `${result.filename}: ${t('file_import_invalid')}`)
      return
    }
    if (projectHasTimelineContent()) {
      setPendingImport({ payload: result.payload, kind: 'json' })
      setImportConfirmOpen(true)
      return
    }
    executeProjectImport(result.payload)
  }

  const handleImportBundleClick = () => {
    if (apiOffline) return
    bundleImportInputRef.current?.click()
  }

  const handleImportBundleFile = async (file: File | undefined) => {
    if (apiOffline || !file) return
    const result = await parseProjectBundleImportFile(file)
    if (!result.ok) {
      const detail = result.detail ? `: ${result.detail}` : ''
      appendEventLog('warn', `${result.filename}: ${t(result.messageKey)}${detail}`)
      return
    }
    if (projectHasTimelineContent()) {
      setPendingImport({
        payload: result.payload,
        importBundleId: result.importBundleId,
        kind: 'bundle',
      })
      setImportConfirmOpen(true)
      return
    }
    executeProjectImport(result.payload, { importBundleId: result.importBundleId })
  }

  const handleExportBundle = async () => {
    if (apiConnectionStatus !== 'connected' || bundleExporting) return
    setBundleExporting(true)
    try {
      const result = await exportProjectBundle()
      if (!result.ok) {
        const detail = result.detail ? `: ${result.detail}` : ''
        appendEventLog('warn', `${t(result.messageKey)}${detail}`)
      }
    } finally {
      setBundleExporting(false)
    }
  }

  const handleImportConfirm = () => {
    if (pendingImport) {
      executeProjectImport(pendingImport.payload, {
        importBundleId: pendingImport.importBundleId ?? null,
      })
    }
    setPendingImport(null)
    setImportConfirmOpen(false)
  }

  const handleStarterSelected = (payload: ProjectImportPayload) => {
    if (apiOffline) return
    if (projectHasTimelineContent()) {
      setGalleryOpen(false)
      setPendingImport({ payload, kind: 'json' })
      setImportConfirmOpen(true)
      return
    }
    executeProjectImport(payload)
    setGalleryOpen(false)
  }

  const runRenderSubmit = async (mode: 'full' | 'preview') => {
    if (apiConnectionStatus !== 'connected' || renderSubmitting) return
    setRenderSubmitting(true)
    try {
      const jobId = await submitCurrentProjectRender(mode)
      openJobsView(jobId)
    } catch (err) {
      appendEventLog(
        'error',
        err instanceof Error ? err.message : t('jobs_submit_failed'),
      )
    } finally {
      setRenderSubmitting(false)
      setQueueConfirmOpen(false)
    }
  }

  const handleRenderSubmit = async (mode: 'full' | 'preview') => {
    if (apiConnectionStatus !== 'connected' || renderSubmitting) return
    try {
      const busy = await projectHasActiveRenderJobs()
      if (busy) {
        setQueueConfirmOpen(true)
        return
      }
      await runRenderSubmit(mode)
    } catch (err) {
      appendEventLog(
        'error',
        err instanceof Error ? err.message : t('jobs_submit_failed'),
      )
    }
  }

  const [queuedRenderMode, setQueuedRenderMode] = useState<'full' | 'preview'>('full')

  const handleQueueConfirm = () => {
    void runRenderSubmit(queuedRenderMode)
  }

  return (
    <header className="flex h-9 items-center border-b border-border bg-background px-2 shrink-0">
      <input
        ref={importInputRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          void handleImportFile(file)
        }}
      />
      <input
        ref={bundleImportInputRef}
        type="file"
        accept=".pixfabrica.zip,application/zip"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          void handleImportBundleFile(file)
        }}
      />
      <span className="mr-4 text-sm font-semibold tracking-tight text-foreground select-none">
        Pixfabrica
      </span>
      <Menubar className="border-none shadow-none bg-transparent h-auto p-0 flex-1">
        <MenubarMenu>
          <MenubarTrigger className="h-7 text-xs">{t('menu_file')}</MenubarTrigger>
          <MenubarContent>
            <MenubarItem onClick={handleNewProject}>{t('file_new')}</MenubarItem>
            <MenubarItem disabled={apiOffline} onClick={() => setGalleryOpen(true)}>
              {t('file_gallery')}
            </MenubarItem>
            {galleryPublishUiEnabled() ? (
              <MenubarItem
                disabled={
                  apiConnectionStatus !== 'connected' ||
                  !hasTimelineContent ||
                  projectValidationBlocked
                }
                onClick={() => setAddToGalleryOpen(true)}
              >
                {t('file_add_to_gallery')}
              </MenubarItem>
            ) : null}
            <MenubarSeparator />
            <MenubarItem disabled={apiOffline} onClick={handleImportClick}>
              {t('file_import_json')}
            </MenubarItem>

            <MenubarItem disabled={apiOffline} onClick={handleImportBundleClick}>
              {t('file_import_bundle')}
            </MenubarItem>
            <MenubarSeparator />
            
            <MenubarItem onClick={exportProjectJson}>{t('file_export_json')}</MenubarItem>

            <MenubarItem
              disabled={apiConnectionStatus !== 'connected' || bundleExporting}
              onClick={() => void handleExportBundle()}
            >
              {bundleExporting ? t('file_bundle_exporting') : t('file_export_bundle')}
            </MenubarItem>
          </MenubarContent>
        </MenubarMenu>

        <MenubarMenu>
          <MenubarTrigger className="h-7 text-xs">{t('menu_edit')}</MenubarTrigger>
          <MenubarContent>
            <MenubarItem disabled={!canUndo} onClick={() => projectUndo()}>
              {t('edit_undo')} <MenubarShortcut>⌘Z</MenubarShortcut>
            </MenubarItem>
            <MenubarItem disabled={!canRedo} onClick={() => projectRedo()}>
              {t('edit_redo')} <MenubarShortcut>⌘⇧Z</MenubarShortcut>
            </MenubarItem>
            <MenubarSeparator />
            <MenubarItem>{t('edit_select_all')}</MenubarItem>
            <MenubarItem>{t('edit_delete_selected')}</MenubarItem>
          </MenubarContent>
        </MenubarMenu>

        <MenubarMenu>
          <MenubarTrigger className="h-7 text-xs">{t('menu_view')}</MenubarTrigger>
          <MenubarContent>
             {pexelsAvailable ? (
              <MenubarItem
                disabled={apiOffline}
                onClick={() => openMenuPhotos()}
              >
                {t('view_stock_photos')}
              </MenubarItem>
            ) : null}
            {pexelsAvailable ? (
              <MenubarItem
                disabled={apiOffline}
                onClick={() => openMenuVideos()}
              >
                {t('view_stock_videos')}
              </MenubarItem>
            ) : null}
            <MenubarItem onClick={toggleLogsPanel}>
              {showLogsPanel ? t('view_hide_event_panel') : t('view_show_event_panel')}
            </MenubarItem>
           
          </MenubarContent>
        </MenubarMenu>

        <MenubarMenu>
          <MenubarTrigger className="h-7 text-xs">{t('menu_render')}</MenubarTrigger>
          <MenubarContent>
            <MenubarItem
              disabled={apiConnectionStatus !== 'connected' || renderSubmitting}
              onClick={() => {
                setQueuedRenderMode('full')
                void handleRenderSubmit('full')
              }}
            >
              {t('render_job')}
            </MenubarItem>
            <MenubarItem
              disabled={apiConnectionStatus !== 'connected' || renderSubmitting}
              onClick={() => {
                setQueuedRenderMode('preview')
                void handleRenderSubmit('preview')
              }}
            >
              {t('render_preview')}
            </MenubarItem>
            <MenubarSeparator />
            <MenubarItem onClick={() => openJobsView()}>{t('render_rendered_jobs')}</MenubarItem>
     
          </MenubarContent>
        </MenubarMenu>

        <MenubarMenu>
          <MenubarTrigger className="h-7 text-xs">{t('menu_settings')}</MenubarTrigger>
          <MenubarContent>
            <MenubarItem onClick={() => setSettingsPanelOpen(true)}>
              {t('settings_open')}
            </MenubarItem>
            <MenubarSeparator />
            <MenubarSub>
              <MenubarSubTrigger>{t('settings_theme')}</MenubarSubTrigger>
              <MenubarSubContent>
                <MenubarRadioGroup
                  value={themeMode}
                  onValueChange={(value) => setThemeMode(value as 'dark' | 'light' | 'system')}
                >
                  <MenubarRadioItem value="light">{t('settings_theme_light')}</MenubarRadioItem>
                  <MenubarRadioItem value="dark">{t('settings_theme_dark')}</MenubarRadioItem>
                  <MenubarRadioItem value="system">{t('settings_theme_system')}</MenubarRadioItem>
                </MenubarRadioGroup>
              </MenubarSubContent>
            </MenubarSub>
            <MenubarSub>
              <MenubarSubTrigger>{t('settings_language')}</MenubarSubTrigger>
              <MenubarSubContent>
                <MenubarRadioGroup
                  value={appSettings.locale}
                  onValueChange={(value) => setAppSettings({ locale: value as UiLocale })}
                >
                  <MenubarRadioItem value="en">English</MenubarRadioItem>
                  <MenubarRadioItem value="es">Español</MenubarRadioItem>
                  <MenubarRadioItem value="ja">日本語</MenubarRadioItem>
                  <MenubarRadioItem value="zh-CN">中文（简体）</MenubarRadioItem>
                </MenubarRadioGroup>
              </MenubarSubContent>
            </MenubarSub>
          </MenubarContent>
        </MenubarMenu>
      </Menubar>

      <span className={`ml-2 rounded px-2 py-0.5 text-[10px] font-medium ${connectionBadgeClass}`}>
        {connectionLabel}
      </span>

      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 ml-auto"
        onClick={toggleThemeMode}
        title={themeTitle}
      >
        <ThemeIcon className="h-4 w-4" />
      </Button>

      <AlertDialog open={newProjectOpen} onOpenChange={setNewProjectOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('file_new_confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('file_new_confirm_body')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('dialog_cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleNewProjectConfirm}>
              {t('file_new')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <ProjectImportConfirmDialog
        open={importConfirmOpen}
        onOpenChange={(open) => {
          setImportConfirmOpen(open)
          if (!open) setPendingImport(null)
        }}
        onConfirm={handleImportConfirm}
        titleKey={
          pendingImport?.kind === 'bundle'
            ? 'file_import_bundle_confirm_title'
            : 'file_import_confirm_title'
        }
        bodyKey="file_import_confirm_body"
        confirmKey={
          pendingImport?.kind === 'bundle' ? 'file_import_bundle' : 'file_import_json'
        }
      />

      <StarterGalleryModal
        open={galleryOpen}
        onOpenChange={setGalleryOpen}
        onStarterSelected={handleStarterSelected}
      />

      <AddToGalleryDialog open={addToGalleryOpen} onOpenChange={setAddToGalleryOpen} />

      <AlertDialog open={queueConfirmOpen} onOpenChange={setQueueConfirmOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('jobs_queue_confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('jobs_queue_confirm_body')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('dialog_cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleQueueConfirm}>
              {t('jobs_queue_confirm_add')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </header>
  )
}
