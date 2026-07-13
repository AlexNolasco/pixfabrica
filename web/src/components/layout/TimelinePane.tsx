import type { ReactNode, UIEvent } from 'react'
import { isClipSelection } from '@/lib/selection'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Play, Pause, SkipBack, Plus, MoreHorizontal, Copy, Trash2,
  ChevronRight, ChevronDown, ArrowUp, ArrowDown, ZoomIn, ZoomOut, Maximize2, RotateCcw,
  Loader2, Volume2, VolumeX, AlertTriangle,
} from 'lucide-react'
import {
  Timeline,
  type TimelineState,
} from '@xzdarcy/react-timeline-editor'

/** Mirrors `@xzdarcy/timeline-engine` (transitive dep; typings not always hoisted). */
interface TimelineActionModel {
  id: string
  start: number
  end: number
  effectId: string
  flexible?: boolean
  movable?: boolean
  minStart?: number
  maxEnd?: number
  selected?: boolean
  disable?: boolean
  pixfabricaClipType?: string
}
interface TimelineRowModel {
  id: string
  actions: TimelineActionModel[]
  rowHeight?: number
}

import {
  DndContext,
  closestCenter,
  PointerSensor,
  useDraggable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { clampSpanToJob, snapTimelineTrim } from '@/lib/timelineSnap'
import { isTransportKeyboardBlocked } from '@/lib/transportKeyboard'
import { timelineAudioEngine } from '@/lib/timelineAudioEngine'
import { prefetchAudioBuffer } from '@/lib/audioBufferCache'
import {
  collectDropFiles,
  dragEventHasFiles,
  firstProjectJsonFile,
  reportTimelineDropFailures,
  reportTimelineDropGuard,
  runTimelineFileDrop,
  runTimelineProjectJsonDrop,
  timelineDropRejectMessage,
} from '@/lib/timelineDrop'
import {
  executeProjectImport,
  projectHasTimelineContent,
  type ProjectImportPayload,
} from '@/lib/projectFileActions'
import { DEFAULT_ANALYZER } from '@/lib/sound'
import {
  canMoveClipToTrack,
  clipDragId,
  clipTrackKind,
} from '@/lib/clipMove'
import { layoutSortId, parseLayoutSortId, resolveTimelineLayout } from '@/lib/timelineLayout'
import {
  TIMELINE_SCALE_WIDTH,
  TIMELINE_START_LEFT,
  computeFitZoomScale,
  formatZoomScaleLabel,
  maxZoomOutScale,
  nextZoomIn,
  nextZoomOut,
  timelineMinScaleCount,
} from '@/lib/timelineZoom'
import { AudioWaveformRender } from '@/components/sound/AudioWaveformRender'
import { SoundLabel } from '@/components/sound/SoundLabel'
import { ProjectImportConfirmDialog } from '@/components/layout/ProjectImportConfirmDialog'
import { COMPOSITION_PREVIEW_CONTROLS_WIDTH_PX } from '@/components/layout/PreviewPane'
import { isCompositionPreviewActive } from '@/lib/compositionPreview'
import { commitPreviewTime, setPlaybackClock } from '@/lib/previewClock'
import { exitClipPreviewForTransport, pauseTransportAt } from '@/lib/previewTransport'
import { isTimelineClipTarget } from '@/lib/timelineScrub'
import { useTimelinePointerScrub } from '@/lib/useTimelinePointerScrub'
import { useT } from '@/lib/i18n'
import {
  clipTimelineIssueWithAssets,
  useTrackTimelineIssueWithAssets,
  type ClipTimelineIssue,
} from '@/lib/prepareWarnings'
import { canAddClipToTrack, canAddTimelineRow } from '@/lib/projectLimits'
import {
  useProjectStore,
  resolvedTrackDuration,
  resolvedSoundDuration,
  resolvedClipDuration,
  newId,
  type Track,
  type Clip,
} from '@/store/projectStore'

type TLEditorRow = TimelineRowModel

// ---- Constants ------------------------------------------------------------

const PIXFABRICA_CLIP_EFFECT_ID = 'pixfabrica-clip'
const PIXFABRICA_CLIP_BROKEN_EFFECT_ID = 'pixfabrica-clip-broken'
const PIXFABRICA_CLIP_INVALID_PARAMS_EFFECT_ID = 'pixfabrica-clip-invalid-params'
const PIXFABRICA_CLIP_MISSING_ASSET_EFFECT_ID = 'pixfabrica-clip-missing-asset'
const TRACK_SPAN_ID_SUFFIX = '::span'

function trackSpanEffectId(trackType: string): string {
  return `pixfabrica-track-span-${trackType}`
}
const CLIP_ROW_SEP = '::clip::'

// ---- Helpers --------------------------------------------------------------

function trackSpanActionId(trackId: string): string {
  return `${trackId}${TRACK_SPAN_ID_SUFFIX}`
}

function isTrackSpanAction(id: string): boolean {
  return id.endsWith(TRACK_SPAN_ID_SUFFIX)
}

function clipRowId(trackId: string, clipId: string): string {
  return `${trackId}${CLIP_ROW_SEP}${clipId}`
}

function parseClipRowId(rowId: string): { trackId: string; clipId: string } | null {
  const idx = rowId.indexOf(CLIP_ROW_SEP)
  if (idx === -1) return null
  return {
    trackId: rowId.slice(0, idx),
    clipId: rowId.slice(idx + CLIP_ROW_SEP.length),
  }
}

type ClipMoveDragData = {
  type: 'clip-move'
  trackId: string
  clipId: string
}

function readClipMoveDragData(data: unknown): ClipMoveDragData | null {
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  if (record.type !== 'clip-move') return null
  if (typeof record.trackId !== 'string') return null
  if (typeof record.clipId !== 'string') return null
  return { type: 'clip-move', trackId: record.trackId, clipId: record.clipId }
}

function isVisualTrack(track: Track): boolean {
  return (track.trackType ?? 'skia') !== 'audio'
}

function visualTrackIdsFromTracks(trackList: Track[]): string[] {
  return trackList.filter(isVisualTrack).map((t) => t.id)
}

/** Front-most first — matches Properties draw order; `clips[0]` stays back in storage. */
function trackClipsDisplayOrder(
  clips: Clip[],
): { el: Clip; storageIndex: number }[] {
  return clips.map((el, storageIndex) => ({ el, storageIndex })).reverse()
}

function clipTypeLabel(clipType: string): string {
  const suffix = clipType.split('.').pop() ?? clipType
  return suffix.replace(/[-_]+/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase())
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.floor((seconds % 1) * 100)
  return `${m}:${String(s).padStart(2, '0')}.${String(ms).padStart(2, '0')}`
}

// ---- Mock data (visual track span label only) ----------------------------

// ---- Track type badge config -----------------------------------------------

const TRACK_TYPE_BADGE: Record<'skia' | 'gl' | 'audio' | 'post', { label: string; className: string }> = {
  skia:  { label: 'Skia',  className: 'bg-blue-500/20 text-blue-400'   },
  gl:    { label: 'GL',    className: 'bg-purple-500/20 text-purple-400' },
  audio: { label: 'Audio', className: 'bg-green-500/20 text-green-400'  },
  post:  { label: 'Post',  className: 'bg-orange-500/20 text-orange-400' },
}

/** Subtle row tint applied to both the label panel and the grid overlay. */
const TRACK_TYPE_ROW_TINT: Record<'skia' | 'gl' | 'audio' | 'post', string> = {
  skia:  'rgba(59,130,246,0.05)',   // blue-500
  gl:    'rgba(168,85,247,0.05)',   // purple-500
  audio: 'rgba(34,197,94,0.05)',    // green-500
  post:  'rgba(249,115,22,0.05)',   // orange-500
}

const TRACK_TYPE_LABEL_BG: Record<'skia' | 'gl' | 'audio' | 'post', string> = {
  skia:  'bg-blue-500/[0.05]',
  gl:    'bg-purple-500/[0.05]',
  audio: 'bg-green-500/[0.05]',
  post:  'bg-orange-500/[0.05]',
}

// ---- ClipLabel ---------------------------------------------------------

function clipEffectIdForIssue(issue: ClipTimelineIssue): string {
  if (issue === 'broken') return PIXFABRICA_CLIP_BROKEN_EFFECT_ID
  if (issue === 'invalid_params') return PIXFABRICA_CLIP_INVALID_PARAMS_EFFECT_ID
  if (issue === 'missing_asset') return PIXFABRICA_CLIP_MISSING_ASSET_EFFECT_ID
  return PIXFABRICA_CLIP_EFFECT_ID
}

function ClipLabel({
  trackId,
  clip,
  index,
  total,
  isSelected,
  isFlashing,
  isPlaying,
  allowReorder,
  allowDuplicate,
  canDuplicate,
  issue,
  onSelect,
  onMoveUp,
  onMoveDown,
  onDuplicate,
  onRemove,
}: {
  trackId: string
  clip: Clip
  index: number
  total: number
  isSelected: boolean
  isFlashing: boolean
  isPlaying: boolean
  allowReorder: boolean
  allowDuplicate: boolean
  canDuplicate: boolean
  issue: ClipTimelineIssue
  onSelect: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  onDuplicate: () => void
  onRemove: () => void
}) {
  const t = useT()
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: clipDragId(trackId, clip.id),
    disabled: isPlaying,
    data: { type: 'clip-move', trackId, clipId: clip.id },
  })
  const label = clip.label || clipTypeLabel(clip.clip_type)
  const showBroken = issue === 'broken'
  const showInvalidParams = issue === 'invalid_params'
  const showMissingAsset = issue === 'missing_asset'
  const clipEnabled = clip.enabled
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      className={`group flex items-center gap-0.5 h-8 pl-4 pr-1 select-none cursor-pointer border-b border-border/40 transition-colors
        ${isDragging ? 'opacity-50' : ''}
        ${!clipEnabled ? 'opacity-55' : ''}
        ${isFlashing ? 'bg-primary/20 ring-1 ring-inset ring-primary/40 text-primary' : ''}
        ${!isFlashing && isSelected ? 'bg-primary/10 text-primary' : ''}
        ${!isFlashing && !isSelected && showBroken ? 'bg-destructive/20 ring-1 ring-inset ring-destructive/40 text-destructive' : ''}
        ${!isFlashing && !isSelected && showInvalidParams ? 'bg-yellow-500/20 ring-1 ring-inset ring-yellow-500/40 text-yellow-700 dark:text-yellow-400' : ''}
        ${!isFlashing && !isSelected && showMissingAsset ? 'bg-orange-500/20 ring-1 ring-inset ring-orange-500/40 text-orange-800 dark:text-orange-300' : ''}
        ${!isFlashing && !isSelected && !showBroken && !showInvalidParams && !showMissingAsset ? 'hover:bg-muted/60 text-muted-foreground' : ''}
      `}
      onClick={onSelect}
    >
      <span
        {...(isPlaying ? {} : listeners)}
        className={`text-muted-foreground hover:text-foreground shrink-0 text-[11px] leading-none ${isPlaying ? 'cursor-default opacity-30' : 'cursor-grab'}`}
        title={isPlaying ? undefined : t('timeline_drag_move_track')}
        onClick={(e) => e.stopPropagation()}
      >
        ⠿
      </span>
      {(showBroken || showInvalidParams || showMissingAsset) && (
        <AlertTriangle
          className={`h-2.5 w-2.5 shrink-0 ${
            showBroken
              ? 'text-destructive'
              : showMissingAsset
                ? 'text-orange-600 dark:text-orange-400'
                : 'text-yellow-600 dark:text-yellow-400'
          }`}
          aria-hidden
        />
      )}
      <span className="text-[10px] truncate flex-1 leading-tight">{label}</span>
      {!clipEnabled && (
        <span className="ml-1 text-[10px] text-muted-foreground shrink-0">{t('timeline_track_off')}</span>
      )}
      {!isPlaying && allowReorder && index < total - 1 && (
        <button
          type="button"
          className="h-4 w-4 grid place-items-center rounded text-muted-foreground hover:text-foreground hover:bg-accent opacity-0 group-hover:opacity-100"
          onClick={(e) => { e.stopPropagation(); onMoveUp() }}
          title={t('timeline_clip_move_up')}
        >
          <ArrowUp className="h-2.5 w-2.5" />
        </button>
      )}
      {!isPlaying && allowReorder && index > 0 && (
        <button
          type="button"
          className="h-4 w-4 grid place-items-center rounded text-muted-foreground hover:text-foreground hover:bg-accent opacity-0 group-hover:opacity-100"
          onClick={(e) => { e.stopPropagation(); onMoveDown() }}
          title={t('timeline_clip_move_down')}
        >
          <ArrowDown className="h-2.5 w-2.5" />
        </button>
      )}
      {!isPlaying && allowDuplicate && (
        <button
          type="button"
          disabled={!canDuplicate}
          className="h-4 w-4 grid place-items-center rounded text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed hover:enabled:text-foreground hover:enabled:bg-accent"
          onClick={(e) => { e.stopPropagation(); if (canDuplicate) onDuplicate() }}
          title={canDuplicate ? t('timeline_clip_duplicate') : t('timeline_clip_duplicate_limit')}
        >
          <Copy className="h-2.5 w-2.5" />
        </button>
      )}
      {!isPlaying && (
        <button
          type="button"
          className="h-4 w-4 grid place-items-center rounded text-muted-foreground hover:text-destructive hover:bg-accent opacity-0 group-hover:opacity-100"
          onClick={(e) => { e.stopPropagation(); onRemove() }}
          title={t('timeline_clip_remove')}
        >
          <Trash2 className="h-2.5 w-2.5" />
        </button>
      )}
    </div>
  )
}

// ---- TrackLabel -----------------------------------------------------------

function TrackLabel({
  track,
  expanded,
  isPlaying,
  isClipDropHighlight,
  onToggleExpand,
  onOpenPluginPicker,
}: {
  track: Track
  expanded: boolean
  isPlaying: boolean
  isClipDropHighlight: boolean
  onToggleExpand: () => void
  onOpenPluginPicker: () => void
}) {
  const t = useT()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: layoutSortId({ kind: 'track', id: track.id }),
    disabled: isPlaying,
  })
  const select = useProjectStore((s) => s.select)
  const removeTrack = useProjectStore((s) => s.removeTrack)
  const duplicateTrack = useProjectStore((s) => s.duplicateTrack)
  const toggleTrackEnabled = useProjectStore((s) => s.toggleTrackEnabled)
  const tracks = useProjectStore((s) => s.tracks)
  const sounds = useProjectStore((s) => s.sounds)
  const pluginPicker = useProjectStore((s) => s.pluginPicker)
  const selection = useProjectStore((s) => s.selection)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const isSelected = selection?.kind === 'track' && selection.trackId === track.id
  const isPickerTarget = pluginPicker?.trackId === track.id
  const canAddClip = canAddClipToTrack(track, serverConfig)
  const canDuplicate = canAddTimelineRow(tracks, sounds, serverConfig)

  const resolvedType = (track.trackType ?? 'skia') as 'skia' | 'gl' | 'post'
  const badge = TRACK_TYPE_BADGE[resolvedType]
  const canPickPlugins = resolvedType === 'skia' || resolvedType === 'gl' || resolvedType === 'post'
  const canOpenPicker = resolvedType === 'post' ? track.enabled : canAddClip
  const addClipTitle =
    resolvedType === 'post'
      ? track.clips.length > 0
        ? t('timeline_change_effect')
        : t('timeline_set_effect')
      : t('timeline_add_clip')
  const trackIssue = useTrackTimelineIssueWithAssets(track)

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      {...attributes}
      className={`group flex items-center gap-0.5 h-8 px-1 select-none cursor-pointer border-b border-border
        ${isDragging ? 'opacity-50' : ''}
        ${isClipDropHighlight ? 'ring-2 ring-inset ring-green-500/50 bg-green-500/10' : ''}
        ${isSelected ? 'bg-primary/10 text-primary' : `${TRACK_TYPE_LABEL_BG[resolvedType]} hover:bg-muted text-foreground`}
        ${!track.enabled ? 'opacity-55' : ''}
      `}
      onClick={() => select({ kind: 'track', trackId: track.id })}
    >
      <button
        type="button"
        className="h-4 w-4 grid place-items-center shrink-0 rounded text-muted-foreground hover:text-foreground"
        onClick={(e) => { e.stopPropagation(); onToggleExpand() }}
        title={expanded ? t('timeline_collapse_clips') : t('timeline_expand_clips')}
      >
        {expanded
          ? <ChevronDown className="h-3 w-3" />
          : <ChevronRight className="h-3 w-3" />}
      </button>

      {/* Drag handle */}
      <span
        {...(isPlaying ? {} : listeners)}
        className={`text-muted-foreground hover:text-foreground shrink-0 text-[11px] leading-none ${isPlaying ? 'cursor-default opacity-30' : 'cursor-grab'}`}
        title={isPlaying ? undefined : t('timeline_drag_reorder')}
      >
        ⠿
      </span>

      {/* Track type badge */}
      <span className={`text-[9px] font-semibold px-1 rounded shrink-0 leading-4 ${badge.className}`}>
        {badge.label}
      </span>

      {/* Label */}
      <span className="text-xs truncate flex-1 ml-0.5 flex items-center gap-1 min-w-0">
        {!expanded && trackIssue === 'broken' && (
          <AlertTriangle
            className="h-3 w-3 shrink-0 text-destructive"
            aria-label={t('prop_plugin_missing')}
          />
        )}
        {!expanded && trackIssue === 'invalid_params' && (
          <AlertTriangle
            className="h-3 w-3 shrink-0 text-yellow-600 dark:text-yellow-400"
            aria-label={t('preview_blocked_invalid_params')}
          />
        )}
        {!expanded && trackIssue === 'missing_asset' && (
          <AlertTriangle
            className="h-3 w-3 shrink-0 text-orange-600 dark:text-orange-400"
            aria-label={t('timeline_missing_asset')}
          />
        )}
        <span className="truncate">{track.label}</span>
        {!track.enabled && <span className="ml-1 text-[10px] text-muted-foreground shrink-0">{t('timeline_track_off')}</span>}
      </span>

      {/* Add clip — expanded tracks only; pinned ring while catalog targets this track */}
      {expanded && canPickPlugins && track.enabled && !isPlaying && canOpenPicker && (
        <button
          type="button"
          className={`h-4 w-4 grid place-items-center rounded shrink-0 transition-colors
            ${isPickerTarget
              ? 'text-primary bg-primary/15 ring-1 ring-primary/30'
              : 'text-primary bg-primary/15 hover:bg-primary/20'
            }`}
          onClick={(e) => {
            e.stopPropagation()
            if (isPickerTarget) return
            onOpenPluginPicker()
          }}
          title={addClipTitle}
        >
          <Plus className="h-3 w-3" />
        </button>
      )}

      {/* Context menu — hidden during playback */}
      {!isPlaying && (
      <DropdownMenu>
        <DropdownMenuTrigger
          className="h-4 w-4 grid place-items-center rounded text-muted-foreground hover:text-foreground hover:bg-accent opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="h-3 w-3" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="bottom" sideOffset={4} className="w-44">
          <DropdownMenuItem onClick={(e) => { e.stopPropagation(); toggleTrackEnabled(track.id) }}>
            {track.enabled ? t('timeline_disable_track') : t('timeline_enable_track')}
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!canDuplicate}
            onClick={(e) => { e.stopPropagation(); duplicateTrack(track.id) }}
          >
            <Copy className="h-3.5 w-3.5" />
            {t('timeline_duplicate_track')}
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onClick={(e) => { e.stopPropagation(); removeTrack(track.id) }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {t('timeline_delete_track')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      )}
    </div>
  )
}

// ---- Main component -------------------------------------------------------

export function TimelinePane() {
  const meta = useProjectStore((s) => s.meta)
  const tracks = useProjectStore((s) => s.tracks)
  const sounds = useProjectStore((s) => s.sounds)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const timelineLayout = useProjectStore((s) => s.timelineLayout)
  const addTrack = useProjectStore((s) => s.addTrack)
  const addSound = useProjectStore((s) => s.addSound)
  const reorderTimelineLayout = useProjectStore((s) => s.reorderTimelineLayout)
  const removeTrack = useProjectStore((s) => s.removeTrack)
  const duplicateTrack = useProjectStore((s) => s.duplicateTrack)
  const openPluginPicker = useProjectStore((s) => s.openPluginPicker)
  const pluginPicker = useProjectStore((s) => s.pluginPicker)
  const setLayoutPrefs = useProjectStore((s) => s.setLayoutPrefs)
  const updateClip = useProjectStore((s) => s.updateClip)
  const removeClip = useProjectStore((s) => s.removeClip)
  const duplicateClip = useProjectStore((s) => s.duplicateClip)
  const moveClip = useProjectStore((s) => s.moveClip)
  const reorderClips = useProjectStore((s) => s.reorderClips)
  const updateTrack = useProjectStore((s) => s.updateTrack)
  const updateSound = useProjectStore((s) => s.updateSound)
  const removeSound = useProjectStore((s) => s.removeSound)
  const duplicateSound = useProjectStore((s) => s.duplicateSound)
  const select = useProjectStore((s) => s.select)
  const selection = useProjectStore((s) => s.selection)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const catalogAddFeedback = useProjectStore((s) => s.catalogAddFeedback)
  const projectLoadEpoch = useProjectStore((s) => s.projectLoadEpoch)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const playing = useProjectStore((s) => s.isPlaying)
  const setPlaying = useProjectStore((s) => s.setIsPlaying)
  const previewTime = useProjectStore((s) => s.previewTime)
  const previewMuted = useProjectStore((s) => s.previewMuted)
  const togglePreviewMuted = useProjectStore((s) => s.togglePreviewMuted)
  const compositionControlsVisible = useProjectStore((s) =>
    isCompositionPreviewActive({
      selection: s.selection,
      tracks: s.tracks,
      appSettings: s.appSettings,
    }),
  )

  const t = useT()
  const catalogLoadStatus = useProjectStore((s) => s.catalogLoadStatus)
  const catalogClips = useProjectStore((s) => s.catalogClips)
  const projectSettings = useProjectStore((s) => s.projectSettings)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  const locale = useProjectStore((s) => s.appSettings.locale)
  const prepareWarnings = useProjectStore((s) => s.prepareWarnings)
  const projectValidation = useMemo(
    () => ({
      tracks,
      projectSettings,
      catalogLoadStatus,
      catalogClips,
      catalogDetailCache,
      locale,
    }),
    [tracks, projectSettings, catalogLoadStatus, catalogClips, catalogDetailCache, locale],
  )
  const [currentTime, setCurrentTime] = useState(previewTime)
  /** Mirrors `currentTime` for the playback loop without listing it in effect deps. */
  const currentTimeRef = useRef(currentTime)
  currentTimeRef.current = currentTime
  const [expandedTrackIds, setExpandedTrackIds] = useState<Set<string>>(new Set())
  const [clipDropHighlightTrackId, setClipDropHighlightTrackId] = useState<string | null>(null)
  const skipProjectLoadExpandRef = useRef(true)
  const [fileDragOver, setFileDragOver] = useState(false)
  const [importProgress, setImportProgress] = useState<{
    current: number
    total: number
    kind?: 'image' | 'video' | 'audio'
  } | null>(
    null,
  )
  const [importConfirmOpen, setImportConfirmOpen] = useState(false)
  const [pendingImport, setPendingImport] = useState<ProjectImportPayload | null>(null)
  const [zoomScale, setZoomScale] = useState(1)
  /** Timeline grid scroll — kept in refs only so auto-scroll during play does not re-render this pane. */
  const scrollLeftRef = useRef(0)
  const scrollTopRef = useRef(0)
  const rowTintScrollerRef = useRef<HTMLDivElement | null>(null)
  const endMarkerRef = useRef<HTMLDivElement | null>(null)
  /** Filled imperatively while `playing` to avoid React commits every frame. */
  const transportTimeElRef = useRef<HTMLSpanElement | null>(null)
  const lastTickRef = useRef<number | null>(null)
  /** Playhead seconds during RAF playback (imperative); avoids setState every frame. */
  const playheadAccumRef = useRef(0)
  const timelineRef = useRef<TimelineState | null>(null)
  const trackLabelsScrollRef = useRef<HTMLDivElement | null>(null)
  const timelineContainerRef = useRef<HTMLDivElement | null>(null)
  const suppressLabelsScrollEmit = useRef(false)
  const trimSnapWholeSecondsRef = useRef(true)
  /** Active timeline drags (spans, clips, playhead, row reorder) — blocks transport + setTime sync. */
  const timelineDragRef = useRef(0)
  /** Playhead scrub only — suppresses RAF `setTime` while transport keeps advancing (B1). */
  const playheadScrubDragRef = useRef(0)
  const zoomScaleRef = useRef(zoomScale)
  zoomScaleRef.current = zoomScale
  const durationRef = useRef(meta.duration)
  durationRef.current = meta.duration

  const beginTimelineDrag = useCallback(() => {
    timelineDragRef.current += 1
  }, [])

  const endTimelineDrag = useCallback(() => {
    timelineDragRef.current = Math.max(0, timelineDragRef.current - 1)
  }, [])

  const commitScrubTime = useCallback((t: number) => {
    pauseTransportAt(t)
    setCurrentTime(t)
    playheadAccumRef.current = t
    timelineRef.current?.setTime(t)
  }, [])

  const beginPlayheadScrub = useCallback(() => {
    beginTimelineDrag()
    playheadScrubDragRef.current += 1
  }, [beginTimelineDrag])

  const endPlayheadScrub = useCallback(
    (t: number) => {
      endTimelineDrag()
      playheadScrubDragRef.current = Math.max(0, playheadScrubDragRef.current - 1)
      commitScrubTime(t)
    },
    [endTimelineDrag, commitScrubTime],
  )

  const previewPlayheadScrub = useCallback((t: number) => {
    timelineRef.current?.setTime(t)
  }, [])

  useTimelinePointerScrub({
    containerRef: timelineContainerRef,
    scrollLeftRef,
    scaleRef: zoomScaleRef,
    durationRef,
    playing,
    onScrubStart: beginPlayheadScrub,
    onScrubPreview: previewPlayheadScrub,
    onScrubEnd: endPlayheadScrub,
  })

  const startTimelineAudio = useCallback(
    (timelineT: number) => {
      void timelineAudioEngine.start({
        timelineT,
        projectDuration: meta.duration,
        sounds,
        meta,
        muted: useProjectStore.getState().previewMuted,
      })
    },
    [meta, sounds],
  )

  const toggleExpand = useCallback((trackId: string) => {
    setExpandedTrackIds((prev) => {
      const next = new Set(prev)
      if (next.has(trackId)) next.delete(trackId)
      else next.add(trackId)
      return next
    })
  }, [])

  const visualTracks = useMemo(() => tracks.filter(isVisualTrack), [tracks])
  const allVisualExpanded =
    visualTracks.length > 0 && visualTracks.every((track) => expandedTrackIds.has(track.id))
  const showExpandCollapseAll = visualTracks.length >= 2

  const toggleExpandAllVisual = useCallback(() => {
    if (allVisualExpanded) {
      setExpandedTrackIds(new Set())
      return
    }
    setExpandedTrackIds(new Set(visualTrackIdsFromTracks(tracks)))
  }, [allVisualExpanded, tracks])

  useEffect(() => {
    if (skipProjectLoadExpandRef.current) {
      skipProjectLoadExpandRef.current = false
      if (projectLoadEpoch === 0) return
    }
    const { tracks: loadedTracks } = useProjectStore.getState()
    setExpandedTrackIds(new Set(visualTrackIdsFromTracks(loadedTracks)))
  }, [projectLoadEpoch])

  useEffect(() => {
    if (!catalogAddFeedback) return
    setExpandedTrackIds((prev) => {
      if (prev.has(catalogAddFeedback.trackId)) return prev
      const next = new Set(prev)
      next.add(catalogAddFeedback.trackId)
      return next
    })
  }, [catalogAddFeedback])

  const layoutDisplay = useMemo(
    () => resolveTimelineLayout(timelineLayout, tracks, sounds),
    [timelineLayout, tracks, sounds]
  )

  const trackById = useMemo(() => new Map(tracks.map((t) => [t.id, t])), [tracks])
  const soundById = useMemo(() => new Map(sounds.map((s) => [s.id, s])), [sounds])

  const tryDuplicateClip = useCallback(
    (trackId: string, clipId: string) => {
      const track = trackById.get(trackId)
      if (!track || (track.trackType ?? 'skia') === 'post') return
      if (!canAddClipToTrack(track, serverConfig)) {
        appendEventLog(
          'warn',
          t('timeline_clip_duplicate_blocked').replace(
            '{max}',
            String(serverConfig.maxClipsPerTrack),
          ),
        )
        return
      }
      duplicateClip(trackId, clipId)
    },
    [trackById, serverConfig, appendEventLog, t, duplicateClip],
  )

  /** Row tint + end marker follow scroll without React state (avoids re-render storms from auto-scroll). */
  const updateScrollDerivedLayout = useCallback(() => {
    const top = scrollTopRef.current
    const left = scrollLeftRef.current
    if (rowTintScrollerRef.current) {
      rowTintScrollerRef.current.style.transform = `translateY(${-top}px)`
    }
    if (endMarkerRef.current) {
      const x =
        TIMELINE_START_LEFT + (meta.duration / zoomScale) * TIMELINE_SCALE_WIDTH - left
      endMarkerRef.current.style.left = `${x}px`
    }
  }, [meta.duration, zoomScale])

  const zoomOut = useCallback(() => {
    setZoomScale((z) => nextZoomOut(z, meta.duration))
  }, [meta.duration])
  const zoomIn = useCallback(() => {
    setZoomScale((z) => nextZoomIn(z))
  }, [])
  const zoomFit = useCallback(() => {
    const el = timelineContainerRef.current
    if (!el) return
    const fit = computeFitZoomScale(meta.duration, el.clientWidth)
    setZoomScale(fit)
    scrollLeftRef.current = 0
    timelineRef.current?.setScrollLeft(0)
    queueMicrotask(updateScrollDerivedLayout)
  }, [meta.duration, updateScrollDerivedLayout])

  useEffect(() => {
    const el = timelineContainerRef.current
    if (!el) return
    const handler = (e: WheelEvent) => {
      if (!e.ctrlKey) return
      e.preventDefault()
      if (e.deltaY > 0) zoomOut()
      else zoomIn()
    }
    el.addEventListener('wheel', handler, { passive: false })
    return () => el.removeEventListener('wheel', handler)
  }, [zoomIn, zoomOut])

  useEffect(() => {
    timelineAudioEngine.setMuted(previewMuted)
  }, [previewMuted])

  useEffect(() => {
    for (const sound of sounds) {
      if (sound.source.trim()) prefetchAudioBuffer(sound.source)
    }
  }, [sounds])

  useEffect(() => {
    const clearStuckDrag = () => {
      queueMicrotask(() => {
        timelineDragRef.current = 0
        playheadScrubDragRef.current = 0
      })
    }
    window.addEventListener('pointerup', clearStuckDrag)
    window.addEventListener('pointercancel', clearStuckDrag)
    return () => {
      window.removeEventListener('pointerup', clearStuckDrag)
      window.removeEventListener('pointercancel', clearStuckDrag)
    }
  }, [])

  useEffect(() => {
    if (playing) return
    if (timelineDragRef.current > 0) return
    setCurrentTime(previewTime)
    playheadAccumRef.current = previewTime
    timelineRef.current?.setTime(previewTime)
  }, [previewTime, playing])

  // Playback loop — imperative playhead + transport text; store clock for preview/audio.
  useEffect(() => {
    if (!playing) {
      lastTickRef.current = null
      return
    }
    playheadAccumRef.current = currentTimeRef.current
    lastTickRef.current = null
    const el = transportTimeElRef.current
    if (el) {
      el.textContent = `${formatTime(playheadAccumRef.current)} / ${formatTime(meta.duration)}`
    }
    let rafId: number
    const tick = (now: number) => {
      if (lastTickRef.current === null) lastTickRef.current = now
      const delta = (now - lastTickRef.current) / 1000
      lastTickRef.current = now
      playheadAccumRef.current += delta
      let next = playheadAccumRef.current
      if (next >= meta.duration) {
        next = meta.duration
        playheadAccumRef.current = next
        if (!playheadScrubDragRef.current) {
          timelineRef.current?.setTime(next)
        }
        commitPreviewTime(next)
        timelineAudioEngine.stop()
        setPlaying(false)
        setCurrentTime(next)
        return
      }
      if (!playheadScrubDragRef.current) {
        timelineRef.current?.setTime(next)
      }
      setPlaybackClock(next)
      const clock = transportTimeElRef.current
      if (clock) {
        clock.textContent = `${formatTime(next)} / ${formatTime(meta.duration)}`
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [playing, meta.duration, setPlaying])

  useEffect(() => {
    if (!playing) {
      timelineAudioEngine.stop()
    }
  }, [playing])

  useEffect(() => () => timelineAudioEngine.stop(), [])

  const togglePlay = useCallback(() => {
    if (!playing) {
      exitClipPreviewForTransport()
      setCurrentTime((t) => {
        const start = t >= meta.duration ? 0 : t
        timelineRef.current?.setTime(start)
        playheadAccumRef.current = start
        commitPreviewTime(start)
        startTimelineAudio(start)
        return start
      })
      setPlaying(true)
    } else {
      timelineAudioEngine.stop()
      const t = playheadAccumRef.current
      commitPreviewTime(t)
      setCurrentTime(t)
      setPlaying(false)
    }
  }, [playing, meta.duration, setPlaying, startTimelineAudio])

  const rewind = useCallback(() => {
    exitClipPreviewForTransport()
    timelineAudioEngine.stop()
    setPlaying(false)
    playheadAccumRef.current = 0
    setCurrentTime(0)
    commitPreviewTime(0)
    timelineRef.current?.setTime(0)
  }, [setPlaying])

  const handleTogglePreviewMuted = useCallback(() => {
    togglePreviewMuted()
  }, [togglePreviewMuted])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const transportKeys = e.key === ' ' || e.key === 'Enter' || e.key === 'Home'
      if (
        transportKeys &&
        (isTransportKeyboardBlocked(e.target) || timelineDragRef.current > 0)
      ) {
        return
      }

      // Transport shortcuts
      if (e.key === ' ') {
        e.preventDefault()
        togglePlay()
        return
      }
      if (e.key === 'Enter' || e.key === 'Home') {
        e.preventDefault()
        rewind()
        return
      }

      const target = e.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return

      // Selection-dependent shortcuts
      if (selection?.kind === 'track') {
        if (e.key === 'Delete' || e.key === 'Backspace') {
          e.preventDefault()
          removeTrack(selection.trackId)
        }
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
          e.preventDefault()
          duplicateTrack(selection.trackId)
        }
      }
      if (selection?.kind === 'sound') {
        if (e.key === 'Delete' || e.key === 'Backspace') {
          e.preventDefault()
          removeSound(selection.soundId)
        }
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
          e.preventDefault()
          duplicateSound(selection.soundId)
        }
      }
      if (isClipSelection(selection) && !playing) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
          e.preventDefault()
          tryDuplicateClip(selection.trackId, selection.clipId)
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    selection,
    playing,
    removeTrack,
    duplicateTrack,
    removeSound,
    duplicateSound,
    tryDuplicateClip,
    togglePlay,
    rewind,
  ])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { trimSnapWholeSecondsRef.current = !e.shiftKey }
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('keyup', onKey)
    }
  }, [])

  const timelineEffects = useMemo(
    () => ({
      [PIXFABRICA_CLIP_EFFECT_ID]: { id: PIXFABRICA_CLIP_EFFECT_ID, name: 'Clip' },
      [PIXFABRICA_CLIP_BROKEN_EFFECT_ID]: { id: PIXFABRICA_CLIP_BROKEN_EFFECT_ID, name: 'Broken clip' },
      [PIXFABRICA_CLIP_INVALID_PARAMS_EFFECT_ID]: {
        id: PIXFABRICA_CLIP_INVALID_PARAMS_EFFECT_ID,
        name: 'Invalid params clip',
      },
      [PIXFABRICA_CLIP_MISSING_ASSET_EFFECT_ID]: {
        id: PIXFABRICA_CLIP_MISSING_ASSET_EFFECT_ID,
        name: 'Missing asset clip',
      },
      ...(['skia', 'gl', 'audio', 'post'] as const).reduce((acc, type) => {
        const id = trackSpanEffectId(type)
        acc[id] = { id, name: `Track span (${type})` }
        return acc
      }, {} as Record<string, { id: string; name: string }>),
    }),
    []
  )

  // Layout rows: interleaved tracks + sounds, plus clip sub-rows when expanded
  const editorData: TLEditorRow[] = useMemo(() => {
    const rows: TLEditorRow[] = []
    for (const entry of layoutDisplay) {
      if (entry.kind === 'sound') {
        const sound = soundById.get(entry.id)
        if (!sound) continue
        const soundDur = resolvedSoundDuration(sound, meta)
        rows.push({
          id: sound.id,
          actions: [{
            id: trackSpanActionId(sound.id),
            start: sound.start,
            end: sound.start + soundDur,
            effectId: trackSpanEffectId('audio'),
            movable: !playing,
            flexible: !playing,
            minStart: 0,
            maxEnd: meta.duration,
          }],
        })
        continue
      }

      const track = trackById.get(entry.id)
      if (!track) continue
      const trackDur = resolvedTrackDuration(track, meta)
      rows.push({
        id: track.id,
        actions: [{
          id: trackSpanActionId(track.id),
          start: track.start,
          end: track.start + trackDur,
          effectId: trackSpanEffectId(track.trackType ?? 'skia'),
          movable: !playing,
          flexible: !playing,
          minStart: 0,
          maxEnd: meta.duration,
        }],
      })
      if (expandedTrackIds.has(track.id)) {
        for (const { el } of trackClipsDisplayOrder(track.clips)) {
          const elDur = resolvedClipDuration(el, track, meta)
          const issue = clipTimelineIssueWithAssets(el, projectValidation, prepareWarnings)
          rows.push({
            id: clipRowId(track.id, el.id),
            actions: [{
              id: el.id,
              start: track.start + el.start,
              end: track.start + el.start + elDur,
              effectId: clipEffectIdForIssue(issue),
              movable: !playing,
              flexible: !playing,
              minStart: track.start,
              maxEnd: track.start + trackDur,
              pixfabricaClipType: el.clip_type,
            }],
          })
        }
      }
    }
    return rows
  }, [layoutDisplay, soundById, trackById, meta, expandedTrackIds, playing, projectValidation, prepareWarnings])

  useLayoutEffect(() => {
    updateScrollDerivedLayout()
  }, [updateScrollDerivedLayout, editorData])

  const applyTrimSnap = useCallback(
    (start: number, end: number) => {
      const snapSec = trimSnapWholeSecondsRef.current
      const s = snapTimelineTrim(start, meta.fps, snapSec)
      const e = snapTimelineTrim(end, meta.fps, snapSec)
      const minLen = 1 / meta.fps
      return clampSpanToJob(s, e, meta.duration, minLen)
    },
    [meta.duration, meta.fps]
  )

  const handleTrackSpanCommit = useCallback(
    (_action: TimelineActionModel, row: TLEditorRow, start: number, end: number) => {
      const rowId = String(row.id)
      const [s, e] = applyTrimSnap(start, end)
      const dur = e - s
      const inheritsProject =
        Math.abs(s) < 1e-4 && Math.abs(dur - meta.duration) < 1 / meta.fps

      if (soundById.has(rowId)) {
        updateSound(rowId, {
          start: inheritsProject ? 0 : s,
          duration: inheritsProject ? null : dur,
        })
        return
      }

      updateTrack(rowId, {
        start: inheritsProject ? 0 : s,
        duration: inheritsProject ? null : dur,
      })
    },
    [applyTrimSnap, meta.duration, meta.fps, soundById, updateSound, updateTrack]
  )

  const handleClipCommit = useCallback(
    (trackId: string, clipId: string, start: number, end: number) => {
      const track = tracks.find((t) => t.id === trackId)
      if (!track) return
      let [s, e] = applyTrimSnap(start, end)
      const minStart = track.start
      const maxEnd = track.start + resolvedTrackDuration(track, meta)
      if (s < minStart) { e += minStart - s; s = minStart }
      if (e > maxEnd) { s -= e - maxEnd; e = maxEnd }
      s = Math.max(minStart, Math.min(s, maxEnd))
      e = Math.max(minStart, Math.min(e, maxEnd))
      if (e <= s) e = Math.min(maxEnd, s + 1 / meta.fps)
      updateClip(trackId, clipId, { start: s - track.start, duration: e - s })
    },
    [tracks, meta, applyTrimSnap, updateClip]
  )

  const handleTimelineActionEnd = useCallback(
    (params: { action: TimelineActionModel; row: TLEditorRow; start: number; end: number }) => {
      const { action, row, start, end } = params
      if (isTrackSpanAction(String(action.id))) {
        handleTrackSpanCommit(action, row, start, end)
        return
      }
      const parsed = parseClipRowId(String(row.id))
      if (parsed) {
        handleClipCommit(parsed.trackId, String(action.id), start, end)
      }
    },
    [handleTrackSpanCommit, handleClipCommit]
  )

  const getActionRender = useCallback(
    (action: TimelineActionModel, row: TLEditorRow): ReactNode => {
      const id = String(action.id)
      if (isTrackSpanAction(id)) {
        const sound = soundById.get(String(row.id))
        if (sound) {
          return <AudioWaveformRender source={sound.source} />
        }
        return (
          <span className="pointer-events-none select-none text-[10px] text-muted-foreground/90">
            {t('timeline_action_track')}
          </span>
        )
      }
      const rawType = action.pixfabricaClipType
      const label = rawType ? clipTypeLabel(rawType) : t('timeline_action_clip')
      return (
        <div className="timeline-clip-label flex h-full min-h-0 items-center px-1 text-[10px] leading-tight text-primary-foreground overflow-hidden rounded-sm">
          <span className="truncate">{label}</span>
        </div>
      )
    },
    [soundById, t]
  )

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }))

  const resolveClipDropTrackId = useCallback((overId: string): string | null => {
    const parsed = parseLayoutSortId(overId)
    return parsed?.kind === 'track' ? parsed.id : null
  }, [])

  const evaluateClipDrop = useCallback(
    (fromTrackId: string, clipId: string, toTrackId: string | null): string | null => {
      if (!toTrackId) return null
      const fromTrack = tracks.find((t) => t.id === fromTrackId)
      const toTrack = tracks.find((t) => t.id === toTrackId)
      const clip = fromTrack?.clips.find((el) => el.id === clipId)
      if (!fromTrack || !toTrack || !clip) return null
      const kind = clipTrackKind(clip.clip_type, catalogClips)
      if (
        !canMoveClipToTrack({
          fromTrackId,
          clip,
          destTrack: toTrack,
          clipTrackKind: kind,
          config: serverConfig,
        })
      ) {
        return null
      }
      return toTrackId
    },
    [tracks, catalogClips, serverConfig],
  )

  const tryMoveClip = useCallback(
    (fromTrackId: string, clipId: string, toTrackId: string | null) => {
      const destTrackId = evaluateClipDrop(fromTrackId, clipId, toTrackId)
      if (!destTrackId) return
      moveClip(fromTrackId, destTrackId, clipId)
      setExpandedTrackIds((prev) => new Set(prev).add(destTrackId))
    },
    [evaluateClipDrop, moveClip],
  )

  const handleClipDragOver = useCallback(
    (event: DragOverEvent) => {
      const payload = readClipMoveDragData(event.active.data.current)
      if (!payload) {
        setClipDropHighlightTrackId(null)
        return
      }
      const toTrackId = event.over
        ? resolveClipDropTrackId(String(event.over.id))
        : null
      setClipDropHighlightTrackId(
        evaluateClipDrop(payload.trackId, payload.clipId, toTrackId),
      )
    },
    [evaluateClipDrop, resolveClipDropTrackId],
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setClipDropHighlightTrackId(null)
      const { active, over } = event
      if (readClipMoveDragData(active.data.current)) {
        if (!over) return
        const payload = readClipMoveDragData(active.data.current)
        if (!payload) return
        tryMoveClip(payload.trackId, payload.clipId, resolveClipDropTrackId(String(over.id)))
        return
      }
      if (!over || active.id === over.id) return
      const fromIndex = layoutDisplay.findIndex(
        (e) => layoutSortId(e) === String(active.id),
      )
      const toIndex = layoutDisplay.findIndex(
        (e) => layoutSortId(e) === String(over.id),
      )
      if (fromIndex !== -1 && toIndex !== -1) reorderTimelineLayout(fromIndex, toIndex)
    },
    [layoutDisplay, reorderTimelineLayout, resolveClipDropTrackId, tryMoveClip],
  )

  const handleAddTrack = useCallback(
    (trackType: 'skia' | 'gl' | 'audio' | 'post') => {
      if (!canAddTimelineRow(tracks, sounds, serverConfig)) return
      if (trackType === 'audio') {
        const id = newId('sound')
        addSound({
          id,
          bus: `Audio ${t('timeline_track_word')} ${sounds.length + 1}`,
          source: '',
          volume: 1,
          seek: 0,
          analyzer: DEFAULT_ANALYZER,
          beat_tightness: 200,
          start: 0,
          duration: null,
          enabled: false,
        })
        return
      }
      const id = newId('track')
      const typeLabel = { skia: 'Skia', gl: 'GL', post: 'Post' }[trackType]
      addTrack({
        id,
        label: `${typeLabel} ${t('timeline_track_word')} ${tracks.length + 1}`,
        enabled: true,
        disableMode: 'bypass_compute',
        start: 0,
        duration: null,
        layout: 'fill',
        trackType,
        clips: [],
      })
      setExpandedTrackIds((prev) => new Set(prev).add(id))
    },
    [tracks, sounds, serverConfig, addTrack, addSound, t]
  )

  const canAddRow = canAddTimelineRow(tracks, sounds, serverConfig)
  const glTracksEnabled = !serverConfig.confirmed || serverConfig.glAvailable

  const handleTimelineScroll = useCallback((params: { scrollTop: number; scrollLeft?: number }) => {
    if (params.scrollLeft !== undefined) scrollLeftRef.current = params.scrollLeft
    scrollTopRef.current = params.scrollTop
    updateScrollDerivedLayout()
    const el = trackLabelsScrollRef.current
    if (!el) return
    if (Math.abs(el.scrollTop - params.scrollTop) < 1) return
    suppressLabelsScrollEmit.current = true
    el.scrollTop = params.scrollTop
    queueMicrotask(() => { suppressLabelsScrollEmit.current = false })
  }, [updateScrollDerivedLayout])

  const handleTrackLabelsScroll = useCallback((e: UIEvent<HTMLDivElement>) => {
    if (suppressLabelsScrollEmit.current) return
    timelineRef.current?.setScrollTop(e.currentTarget.scrollTop)
  }, [])

  const handleFileDragEnter = useCallback((e: React.DragEvent) => {
    if (!dragEventHasFiles(e.dataTransfer)) return
    e.preventDefault()
    setFileDragOver(true)
  }, [])

  const handleFileDragOver = useCallback((e: React.DragEvent) => {
    if (!dragEventHasFiles(e.dataTransfer)) return
    e.preventDefault()
    setFileDragOver(true)
  }, [])

  const handleFileDragLeave = useCallback((e: React.DragEvent) => {
    if (!dragEventHasFiles(e.dataTransfer)) return
    e.preventDefault()
    setFileDragOver(false)
  }, [])

  const handleFileDrop = useCallback(
    async (e: React.DragEvent) => {
      if (!dragEventHasFiles(e.dataTransfer)) return
      e.preventDefault()
      setFileDragOver(false)
      if (importProgress) return

      const droppedFiles = await collectDropFiles(e.dataTransfer)

      const jsonFile = firstProjectJsonFile(droppedFiles)
      if (jsonFile) {
        const dropResult = await runTimelineProjectJsonDrop(jsonFile)
        if (dropResult.kind === 'playing' || dropResult.kind === 'preview_stop_timeout') {
          reportTimelineDropGuard(timelineDropRejectMessage(dropResult.kind))
          return
        }
        if (dropResult.kind === 'invalid') {
          reportTimelineDropGuard(`${dropResult.filename}: ${t('file_import_invalid')}`)
          return
        }
        if (projectHasTimelineContent()) {
          setPendingImport(dropResult.payload)
          setImportConfirmOpen(true)
          return
        }
        executeProjectImport(dropResult.payload)
        return
      }

      const { rejected, result } = await runTimelineFileDrop(droppedFiles, (current, total, kind) => {
        setImportProgress({ current, total, kind })
      })
      setImportProgress(null)

      if (rejected) {
        reportTimelineDropGuard(timelineDropRejectMessage(rejected))
        return
      }

      if (result.frontTrackId) {
        setExpandedTrackIds(new Set([result.frontTrackId]))
      }
      if (result.frontTrackId || result.frontSoundId) {
        setLayoutPrefs({ rightCollapsed: false })
      }

      reportTimelineDropFailures(result.failed, result.succeeded)
    },
    [importProgress, setLayoutPrefs, t],
  )

  const handleImportConfirm = useCallback(() => {
    if (pendingImport) {
      executeProjectImport(pendingImport)
    }
    setPendingImport(null)
    setImportConfirmOpen(false)
  }, [pendingImport])

  const showDropChrome = fileDragOver && !importProgress && !playing
  const importing = importProgress !== null

  return (
    <div className="flex flex-col h-full min-h-0 bg-background select-none">
      {/* Transport bar */}
      <div className="flex items-center gap-2 px-3 py-1 border-b border-border shrink-0">
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={rewind}>
          <SkipBack className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={togglePlay} title={!playing && currentTime >= meta.duration ? t('timeline_replay') : undefined}>
          {playing
            ? <Pause className="h-3.5 w-3.5" />
            : currentTime >= meta.duration
              ? <RotateCcw className="h-3.5 w-3.5" />
              : <Play className="h-3.5 w-3.5" />}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={handleTogglePreviewMuted}
          title={previewMuted ? t('timeline_preview_unmute') : t('timeline_preview_mute')}
        >
          {previewMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
        </Button>
        <span className="text-xs font-mono text-muted-foreground">
          {playing ? (
            <span ref={transportTimeElRef} />
          ) : (
            <>
              {formatTime(currentTime)} / {formatTime(meta.duration)}
            </>
          )}
        </span>
        <span className="text-[10px] text-muted-foreground hidden sm:inline shrink-0">
          {t('timeline_hint')}
        </span>
        <div className="flex-1" />
        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={zoomOut}
            disabled={zoomScale >= maxZoomOutScale(meta.duration) - 0.001}
            title={t('timeline_zoom_out')}
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={zoomFit}
            disabled={meta.duration <= 0}
            title={t('timeline_zoom_fit')}
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </Button>
          <span className="text-[10px] text-muted-foreground min-w-[2.75rem] text-center tabular-nums">
            {formatZoomScaleLabel(zoomScale)}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={zoomIn}
            disabled={zoomScale <= 1}
            title={t('timeline_zoom_in')}
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger
            disabled={!canAddRow || playing}
            className={`inline-flex items-center gap-1 h-6 px-2 text-xs rounded transition-colors bg-primary/10 text-primary ${!canAddRow || playing ? 'opacity-40 pointer-events-none' : 'hover:bg-primary/15'}`}
          >
            <Plus className="h-3 w-3" />
            {t('track_add')}
            <ChevronDown className="h-3 w-3" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" sideOffset={4} className="w-52">
            <DropdownMenuItem disabled={!canAddRow} onClick={() => handleAddTrack('skia')}>
              <span className="text-[9px] font-semibold px-1 rounded bg-blue-500/20 text-blue-400 mr-1.5 leading-4">Skia</span>
              {t('track_skia_desc')}
            </DropdownMenuItem>
            <DropdownMenuItem disabled={!canAddRow || !glTracksEnabled} onClick={() => handleAddTrack('gl')}>
              <span className="text-[9px] font-semibold px-1 rounded bg-purple-500/20 text-purple-400 mr-1.5 leading-4">GL</span>
              {t('track_gl_desc')}
            </DropdownMenuItem>
            <DropdownMenuItem disabled={!canAddRow || !glTracksEnabled} onClick={() => handleAddTrack('post')}>
              <span className="text-[9px] font-semibold px-1 rounded bg-orange-500/20 text-orange-400 mr-1.5 leading-4">Post</span>
              {t('track_post_desc')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={!canAddRow} onClick={() => handleAddTrack('audio')}>
              <span className="text-[9px] font-semibold px-1 rounded bg-green-500/20 text-green-400 mr-1.5 leading-4">Audio</span>
              {t('track_audio_desc')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Track labels + timeline grid */}
      <div
        className="relative flex flex-1 overflow-hidden"
        onDragEnter={handleFileDragEnter}
        onDragOver={handleFileDragOver}
        onDragLeave={handleFileDragLeave}
        onDrop={handleFileDrop}
      >
        {(showDropChrome || importing) && (
          <div
            className={`absolute inset-0 z-30 flex flex-col items-center justify-center gap-2 pointer-events-none ${
              importing ? 'bg-background/80' : 'bg-primary/10 border-2 border-dashed border-primary/50'
            }`}
            aria-live="polite"
          >
            {importing ? (
              <>
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-sm font-medium text-foreground">
                  {importProgress.kind === 'video'
                    ? t('timeline_drop_optimizing_video')
                    : importProgress.kind === 'audio'
                      ? t('timeline_drop_optimizing_audio')
                      : t('timeline_drop_importing')}
                </p>
                <p className="text-xs text-muted-foreground font-mono">
                  {importProgress.current} / {importProgress.total}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground px-4 text-center">
                {apiConnectionStatus === 'connected'
                  ? t('timeline_drop_hint')
                  : t('timeline_drop_api_offline')}
              </p>
            )}
          </div>
        )}
        <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left: sortable track labels + clip sub-labels */}
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={beginTimelineDrag}
          onDragOver={handleClipDragOver}
          onDragCancel={() => {
            endTimelineDrag()
            setClipDropHighlightTrackId(null)
          }}
          onDragEnd={(event) => {
            endTimelineDrag()
            handleDragEnd(event)
          }}
        >
          <SortableContext
            items={layoutDisplay.map((e) => layoutSortId(e))}
            strategy={verticalListSortingStrategy}
          >
            <div
              ref={trackLabelsScrollRef}
              className="timeline-pane-track-labels w-44 shrink-0 border-r border-border overflow-y-auto"
              onScroll={handleTrackLabelsScroll}
            >
              {/* Header row aligns with timeline scale bar */}
              <div className="h-8 border-b border-border flex items-center justify-end px-1">
                {showExpandCollapseAll ? (
                  <button
                    type="button"
                    className="shrink-0 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                    onClick={toggleExpandAllVisual}
                  >
                    {allVisualExpanded ? t('timeline_collapse_all') : t('timeline_expand_all')}
                  </button>
                ) : null}
              </div>
              {layoutDisplay.flatMap((entry) => {
                if (entry.kind === 'sound') {
                  const sound = soundById.get(entry.id)
                  if (!sound) return []
                  return [
                    <SoundLabel key={sound.id} sound={sound} isPlaying={playing} />,
                  ] as ReactNode[]
                }

                const track = trackById.get(entry.id)
                if (!track) return []
                const expanded = expandedTrackIds.has(track.id)
                const rows: ReactNode[] = [
                  <TrackLabel
                    key={track.id}
                    track={track}
                    expanded={expanded}
                    isPlaying={playing}
                    isClipDropHighlight={clipDropHighlightTrackId === track.id}
                    onToggleExpand={() => toggleExpand(track.id)}
                    onOpenPluginPicker={() => {
                      const isPostTrack = (track.trackType ?? 'skia') === 'post'
                      if (!isPostTrack && !canAddClipToTrack(track, serverConfig)) return
                      if (pluginPicker?.trackId === track.id) return
                      if (!expandedTrackIds.has(track.id)) {
                        setExpandedTrackIds((prev) => new Set(prev).add(track.id))
                      }
                      const kind =
                        track.trackType === 'gl' || track.trackType === 'post'
                          ? track.trackType
                          : 'skia'
                      select({ kind: 'track', trackId: track.id })
                      openPluginPicker(track.id, kind)
                      setLayoutPrefs({ rightCollapsed: false })
                    }}
                  />,
                ]
                if (expanded) {
                  const isPostTrack = (track.trackType ?? 'skia') === 'post'
                  const canDuplicateClip = canAddClipToTrack(track, serverConfig)
                  for (const { el, storageIndex } of trackClipsDisplayOrder(track.clips)) {
                    const issue = clipTimelineIssueWithAssets(el, projectValidation, prepareWarnings)
                    rows.push(
                      <ClipLabel
                        key={`${track.id}::${el.id}`}
                        trackId={track.id}
                        clip={el}
                        index={storageIndex}
                        total={track.clips.length}
                        issue={issue}
                        isSelected={
                          isClipSelection(selection) &&
                          selection.trackId === track.id &&
                          selection.clipId === el.id
                        }
                        isFlashing={
                          catalogAddFeedback?.trackId === track.id &&
                          catalogAddFeedback.clipId === el.id
                        }
                        isPlaying={playing}
                        allowReorder={!isPostTrack}
                        allowDuplicate={!isPostTrack}
                        canDuplicate={canDuplicateClip}
                        onSelect={() => {
                          select({ kind: 'clip', trackId: track.id, clipId: el.id })
                          void useProjectStore.getState().hydrateClipDefaults(
                            track.id,
                            el.id,
                            el.clip_type,
                          )
                        }}
                        onMoveUp={() =>
                          reorderClips(track.id, storageIndex, storageIndex + 1)
                        }
                        onMoveDown={() =>
                          reorderClips(track.id, storageIndex, storageIndex - 1)
                        }
                        onDuplicate={() => tryDuplicateClip(track.id, el.id)}
                        onRemove={() => removeClip(track.id, el.id)}
                      />
                    )
                  }
                }
                return rows as ReactNode[]
              })}
            </div>
          </SortableContext>
        </DndContext>

        {/* Right: timeline editor */}
        <div
          ref={timelineContainerRef}
          className="flex-1 min-h-0 overflow-hidden relative"
        >
          {/* Row tint overlay — one strip per editorData row, scrolls with the grid */}
          <div className="pointer-events-none absolute inset-0 overflow-hidden z-0">
            <div style={{ height: 32 }} />
            <div ref={rowTintScrollerRef} style={{ willChange: 'transform' }}>
              {editorData.map((row) => {
                const parsed = parseClipRowId(String(row.id))
                const sound = soundById.get(String(row.id))
                const trackId = parsed ? parsed.trackId : String(row.id)
                const track = trackById.get(trackId)
                const type = sound
                  ? 'audio'
                  : ((track?.trackType ?? 'skia') as 'skia' | 'gl' | 'audio' | 'post')
                return (
                  <div key={row.id} style={{ height: 32, background: TRACK_TYPE_ROW_TINT[type] }} />
                )
              })}
            </div>
          </div>
          <Timeline
            rowHeight={32}
            ref={timelineRef}
            editorData={editorData}
            effects={timelineEffects}
            scale={zoomScale}
            minScaleCount={timelineMinScaleCount(meta.duration, zoomScale)}
            onCursorDragStart={() => {
              beginPlayheadScrub()
            }}
            onCursorDragEnd={(t) => {
              endPlayheadScrub(t)
            }}
            onClickTimeArea={(time) => {
              if (playing) return false
              commitScrubTime(time)
            }}
            onClickRow={(e, { time }) => {
              if (playing) return
              if (isTimelineClipTarget(e.target)) return
              commitScrubTime(time)
            }}
            onActionMoveStart={beginTimelineDrag}
            onActionMoveEnd={(params) => {
              endTimelineDrag()
              handleTimelineActionEnd(params)
            }}
            onActionResizeStart={beginTimelineDrag}
            onActionResizeEnd={(params) => {
              endTimelineDrag()
              handleTimelineActionEnd(params)
            }}
            getActionRender={getActionRender}
            onClickAction={(_e, { action, row }) => {
              const aid = String(action.id)
              const rid = String(row.id)
              if (isTrackSpanAction(aid)) {
                if (soundById.has(rid)) {
                  select({ kind: 'sound', soundId: rid })
                } else {
                  select({ kind: 'track', trackId: rid })
                }
                return
              }
              const parsed = parseClipRowId(rid)
              if (parsed) {
                select({ kind: 'clip', trackId: parsed.trackId, clipId: aid })
              }
            }}
            onScroll={handleTimelineScroll}
            style={{ width: '100%', height: '100%' }}
          />
          {/* End-of-video marker — `left` updated from scroll refs in `updateScrollDerivedLayout` */}
          <div
            ref={endMarkerRef}
            className="pointer-events-none absolute top-0 bottom-0 z-20 flex flex-col"
          >
            <div className="h-8 flex items-center pl-1.5">
              <span className="text-[9px] text-muted-foreground/70 select-none whitespace-nowrap font-mono">
                {formatTime(meta.duration)}
              </span>
            </div>
            <div className="flex-1 border-l-2 border-dashed border-muted-foreground/40" />
          </div>
        </div>
        {compositionControlsVisible ? (
          <div
            className="shrink-0 border-l border-border bg-muted/20"
            style={{ width: COMPOSITION_PREVIEW_CONTROLS_WIDTH_PX }}
            aria-hidden
          />
        ) : null}
        </div>
      </div>

      <ProjectImportConfirmDialog
        open={importConfirmOpen}
        onOpenChange={(open) => {
          setImportConfirmOpen(open)
          if (!open) setPendingImport(null)
        }}
        onConfirm={handleImportConfirm}
      />
    </div>
  )
}
