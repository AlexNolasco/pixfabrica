import { Copy, MoreHorizontal, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { layoutSortId } from '@/lib/timelineLayout'
import { canAddTimelineRow } from '@/lib/projectLimits'
import { useT } from '@/lib/i18n'
import type { Sound } from '@/lib/sound'
import { useSoundIsAnalyzing } from '@/hooks/useAudioAnalysisCoordinator'
import { useProjectStore } from '@/store/projectStore'

const AUDIO_BADGE = 'bg-green-500/20 text-green-400'
const AUDIO_LABEL_BG = 'bg-green-500/[0.05]'

export function SoundLabel({
  sound,
  isPlaying,
}: {
  sound: Sound
  isPlaying: boolean
}) {
  const t = useT()
  const select = useProjectStore((s) => s.select)
  const updateSound = useProjectStore((s) => s.updateSound)
  const removeSound = useProjectStore((s) => s.removeSound)
  const duplicateSound = useProjectStore((s) => s.duplicateSound)
  const tracks = useProjectStore((s) => s.tracks)
  const sounds = useProjectStore((s) => s.sounds)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const toggleSoundEnabled = useProjectStore((s) => s.toggleSoundEnabled)
  const canDuplicate = canAddTimelineRow(tracks, sounds, serverConfig)
  const selection = useProjectStore((s) => s.selection)
  const isSelected = selection?.kind === 'sound' && selection.soundId === sound.id
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(sound.bus)
  const inputRef = useRef<HTMLInputElement>(null)

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: layoutSortId({ kind: 'sound', id: sound.id }),
    disabled: isPlaying,
  })

  useEffect(() => {
    if (!editing) setDraft(sound.bus)
  }, [sound.bus, editing])

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const commitRename = () => {
    setEditing(false)
    updateSound(sound.id, { bus: draft })
  }

  const isAnalyzing = useSoundIsAnalyzing(sound.id)
  const displayName = sound.bus.trim() || t('sound_untitled')

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      {...attributes}
      className={`group flex items-center gap-0.5 h-8 px-1 select-none cursor-pointer border-b border-border
        ${isDragging ? 'opacity-50' : ''}
        ${isSelected ? 'bg-primary/10 text-primary' : `${AUDIO_LABEL_BG} hover:bg-muted text-foreground`}
        ${!sound.enabled ? 'opacity-55' : ''}
      `}
      onClick={() => select({ kind: 'sound', soundId: sound.id })}
    >
      <span className="h-4 w-4 shrink-0" />

      <span
        {...(isPlaying ? {} : listeners)}
        className={`text-muted-foreground hover:text-foreground shrink-0 text-[11px] leading-none ${isPlaying ? 'cursor-default opacity-30' : 'cursor-grab'}`}
        title={isPlaying ? undefined : t('timeline_drag_reorder')}
      >
        ⠿
      </span>

      <span className={`text-[9px] font-semibold px-1 rounded shrink-0 leading-4 ${AUDIO_BADGE}`}>
        Audio
      </span>

      {editing ? (
        <input
          ref={inputRef}
          className="text-xs flex-1 min-w-0 rounded border border-border bg-background px-1 py-0 select-text"
          value={draft}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitRename()
            if (e.key === 'Escape') {
              setDraft(sound.bus)
              setEditing(false)
            }
          }}
        />
      ) : (
        <span
          className="text-xs truncate flex-1 ml-0.5"
          onDoubleClick={(e) => {
            e.stopPropagation()
            if (!isPlaying) setEditing(true)
          }}
        >
          {displayName}
          {isAnalyzing ? (
            <span className="ml-1 text-[10px] text-muted-foreground">{t('sound_analyzing')}</span>
          ) : null}
          {!sound.enabled && (
            <span className="ml-1 text-[10px] text-muted-foreground">{t('timeline_track_off')}</span>
          )}
        </span>
      )}

      {!isPlaying && (
        <DropdownMenu>
          <DropdownMenuTrigger
            className="h-4 w-4 grid place-items-center rounded text-muted-foreground hover:text-foreground hover:bg-accent opacity-0 group-hover:opacity-100 transition-opacity"
            onClick={(e) => e.stopPropagation()}
          >
            <MoreHorizontal className="h-3 w-3" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="bottom" sideOffset={4} className="w-44">
            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); toggleSoundEnabled(sound.id) }}>
              {sound.enabled ? t('timeline_disable_track') : t('timeline_enable_track')}
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={!canDuplicate}
              onClick={(e) => { e.stopPropagation(); duplicateSound(sound.id) }}
            >
              <Copy className="h-3.5 w-3.5" />
              {t('timeline_duplicate_track')}
            </DropdownMenuItem>
            <DropdownMenuItem
              variant="destructive"
              onClick={(e) => { e.stopPropagation(); removeSound(sound.id) }}
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
