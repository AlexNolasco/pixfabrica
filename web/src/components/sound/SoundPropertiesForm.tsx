import { ChevronDown, ChevronUp, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { fetchAudioBuffer, prefetchAudioBuffer } from '@/lib/audioBufferCache'
import { formatTime } from '@/lib/formatTime'
import { acceptAttribute, apiUploadMedia, formatMaxBytes } from '@/lib/mediaUpload'
import {
  duplicateBusNames,
  soundHasRequirements,
  type Sound,
} from '@/lib/sound'
import { computeFitProjectDuration } from '@/lib/soundFit'
import { useT } from '@/lib/i18n'
import { isLosslessAudioFile } from '@/lib/timelineDrop/classify'
import { uploadMaxBytes } from '@/lib/serverConfig'
import { useProjectStore } from '@/store/projectStore'

const AUDIO_ACCEPT = ['.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac']

type DecodeState = 'idle' | 'loading' | 'ready' | 'error'

export function SoundPropertiesForm({
  sound,
  allSounds,
}: {
  sound: Sound
  allSounds: Sound[]
}) {
  const t = useT()
  const meta = useProjectStore((s) => s.meta)
  const updateSound = useProjectStore((s) => s.updateSound)
  const applyFitProjectToSound = useProjectStore((s) => s.applyFitProjectToSound)
  const toggleSoundEnabled = useProjectStore((s) => s.toggleSoundEnabled)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const audioMaxBytes = uploadMaxBytes('audio', serverConfig)
  const audioLosslessMaxBytes = uploadMaxBytes('audio_lossless', serverConfig)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [showSourceUrl, setShowSourceUrl] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [decodeState, setDecodeState] = useState<DecodeState>('idle')
  const [bufferDuration, setBufferDuration] = useState<number | null>(null)
  const [shortenConfirmOpen, setShortenConfirmOpen] = useState(false)
  const [pendingFitDuration, setPendingFitDuration] = useState<number | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const valid = soundHasRequirements(sound)
  const dupes = duplicateBusNames(allSounds)
  const isDuplicate = sound.bus.trim().length > 0 && dupes.has(sound.bus.trim())

  const fitDuration =
    bufferDuration != null
      ? computeFitProjectDuration(bufferDuration, sound, meta.fps)
      : null

  useEffect(() => {
    if (!valid) {
      setDecodeState('idle')
      setBufferDuration(null)
      return
    }
    let cancelled = false
    setDecodeState('loading')
    setBufferDuration(null)
    void fetchAudioBuffer(sound.source).then((buf) => {
      if (cancelled) return
      if (!buf || buf.duration <= 0) {
        setDecodeState('error')
        setBufferDuration(null)
        return
      }
      setBufferDuration(buf.duration)
      setDecodeState('ready')
    })
    return () => {
      cancelled = true
    }
  }, [sound.source, valid])

  const applyFit = useCallback(
    (duration: number) => {
      applyFitProjectToSound(sound.id, duration)
      setShortenConfirmOpen(false)
      setPendingFitDuration(null)
    },
    [applyFitProjectToSound, sound.id],
  )

  const onFitClick = useCallback(() => {
    if (fitDuration == null) return
    const { meta: jobMeta, applyFitProjectToSound: applyFitAction } =
      useProjectStore.getState()
    if (fitDuration < jobMeta.duration - 1e-6) {
      setPendingFitDuration(fitDuration)
      setShortenConfirmOpen(true)
      return
    }
    applyFitAction(sound.id, fitDuration)
  }, [fitDuration, sound.id])

  const onUpload = useCallback(
    async (file: File) => {
      setUploadError(null)
      const maxBytes = isLosslessAudioFile(file) ? audioLosslessMaxBytes : audioMaxBytes
      if (file.size > maxBytes) {
        setUploadError(
          `${t('param_file_too_large')} (${formatMaxBytes(maxBytes)})`,
        )
        return
      }
      setUploading(true)
      try {
        const res = await apiUploadMedia(file, 'audio')
        updateSound(sound.id, { source: res.path })
        prefetchAudioBuffer(res.path)
      } catch (e) {
        setUploadError(e instanceof Error ? e.message : t('sound_upload_failed'))
      } finally {
        setUploading(false)
      }
    },
    [audioLosslessMaxBytes, audioMaxBytes, sound.id, t, updateSound],
  )

  const spanLabel =
    sound.duration != null ? `${sound.duration}s` : t('prop_inherited')

  return (
    <div className="flex flex-col gap-2">
      <Field label={t('sound_bus_name')}>
        <input
          type="text"
          className="rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60 w-full"
          value={sound.bus}
          onChange={(e) => updateSound(sound.id, { bus: e.target.value })}
          placeholder={t('sound_bus_placeholder')}
        />
      </Field>
      {isDuplicate ? (
        <p className="text-[10px] text-amber-600 dark:text-amber-400 leading-snug">
          {t('sound_duplicate_bus_warning')}
        </p>
      ) : null}
      {!sound.bus.trim() ? (
        <p className="text-[10px] text-muted-foreground">{t('sound_name_required')}</p>
      ) : null}

      <Field label={t('sound_source')}>
        <input
          ref={fileRef}
          type="file"
          accept={acceptAttribute(AUDIO_ACCEPT)}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void onUpload(file)
            e.target.value = ''
          }}
        />
        <div className="flex flex-col gap-1">
          <button
            type="button"
            disabled={uploading}
            className="inline-flex items-center gap-1.5 rounded border border-border px-2 py-1.5 text-xs hover:bg-muted/60 disabled:opacity-50"
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="h-3.5 w-3.5" />
            {uploading ? t('param_file_uploading') : t('sound_upload_audio')}
          </button>
          <p className="text-[10px] text-muted-foreground">
            {t('sound_upload_limit')} ({formatMaxBytes(audioMaxBytes)}, WAV/FLAC {formatMaxBytes(audioLosslessMaxBytes)})
          </p>
          {sound.source ? (
            <p className="text-[10px] font-mono text-foreground truncate" title={sound.source}>
              {sound.source}
            </p>
          ) : (
            <p className="text-[10px] text-muted-foreground">{t('sound_source_required')}</p>
          )}
          {uploadError ? (
            <p className="text-[10px] text-destructive">{uploadError}</p>
          ) : null}
          <button
            type="button"
            className="text-[10px] text-muted-foreground hover:text-foreground text-left w-fit"
            onClick={() => setShowSourceUrl((v) => !v)}
          >
            {showSourceUrl ? t('sound_hide_url') : t('sound_show_url')}
          </button>
          {showSourceUrl ? (
            <input
              type="text"
              className="rounded border border-border bg-background px-2 py-1 text-xs font-mono outline-none focus:border-primary/60 w-full"
              value={sound.source}
              placeholder="https://… or local path"
              onChange={(e) => updateSound(sound.id, { source: e.target.value })}
            />
          ) : null}
        </div>
      </Field>

      <Field label={t('sound_volume')}>
        <div className="flex items-center gap-2">
          <Slider
            min={0}
            max={100}
            step={1}
            value={[Math.min(100, Math.round(sound.volume * 100))]}
            onValueChange={(v) => {
              const n = Array.isArray(v) ? v[0] : v
              const pct = Math.min(100, Math.max(0, n ?? 100))
              updateSound(sound.id, { volume: pct / 100 })
            }}
            className="flex-1"
          />
          <span className="text-[10px] font-mono text-muted-foreground w-8 text-right">
            {Math.min(100, Math.round(sound.volume * 100))}%
          </span>
        </div>
      </Field>

      <Field label={t('sound_seek')}>
        <input
          type="number"
          min={0}
          step={0.1}
          className="rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60 w-full"
          value={sound.seek}
          onChange={(e) => updateSound(sound.id, { seek: Math.max(0, Number(e.target.value) || 0) })}
        />
        <p className="text-[10px] text-muted-foreground mt-0.5">{t('sound_seek_hint')}</p>
      </Field>

      <div className="flex items-center justify-between rounded border border-border px-2 py-1.5">
        <span className="text-muted-foreground">{t('prop_enabled')}</span>
        <button
          type="button"
          disabled={!valid}
          className={`rounded px-2 py-0.5 text-[11px] ${
            sound.enabled && valid
              ? 'bg-primary/15 text-primary hover:bg-primary/20'
              : 'bg-muted text-muted-foreground hover:bg-muted/80'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
          onClick={() => toggleSoundEnabled(sound.id)}
        >
          {sound.enabled && valid ? t('prop_on') : t('prop_off')}
        </button>
      </div>

      <Field label={t('prop_start')} value={`${sound.start}s`} />

      <div className="flex flex-col gap-1">
        <span className="text-muted-foreground">{t('left_duration')}</span>
        <span className="text-foreground">{spanLabel}</span>
        {valid && decodeState === 'loading' ? (
          <p className="text-[10px] text-muted-foreground">{t('sound_fit_decode_loading')}</p>
        ) : null}
        {valid && decodeState === 'error' ? (
          <p className="text-[10px] text-destructive">{t('sound_fit_decode_failed')}</p>
        ) : null}
        {valid && decodeState === 'ready' && bufferDuration != null && fitDuration != null ? (
          <p className="text-[10px] text-muted-foreground">
            {t('sound_fit_duration_hint')
              .replace('{file}', formatTime(bufferDuration))
              .replace('{project}', formatTime(fitDuration))}
          </p>
        ) : null}
        <button
          type="button"
          disabled={!valid || decodeState !== 'ready' || fitDuration == null}
          className="mt-0.5 w-fit rounded border border-border px-2 py-1 text-xs hover:bg-muted/60 disabled:opacity-40 disabled:cursor-not-allowed"
          onClick={onFitClick}
        >
          {t('sound_fit_project_duration')}
        </button>
      </div>

      <AlertDialog open={shortenConfirmOpen} onOpenChange={setShortenConfirmOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('sound_fit_shorten_confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingFitDuration != null
                ? t('sound_fit_shorten_confirm_body')
                    .replace('{current}', formatTime(meta.duration))
                    .replaceAll('{next}', formatTime(pendingFitDuration))
                : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('dialog_cancel')}</AlertDialogCancel>
            <Button
              variant="destructive"
              onClick={() => {
                if (pendingFitDuration != null) applyFit(pendingFitDuration)
              }}
            >
              {t('sound_fit_project_duration')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <button
        type="button"
        className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground"
        onClick={() => setAdvancedOpen((v) => !v)}
      >
        {advancedOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        {t('sound_advanced')}
      </button>
      {advancedOpen ? (
        <div className="flex flex-col gap-2 rounded border border-border px-2 py-2">
          <Field label={t('sound_beat_tightness')}>
            <input
              type="number"
              min={1}
              max={1000}
              step={1}
              className="rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60 w-full"
              value={sound.beat_tightness}
              onChange={(e) =>
                updateSound(sound.id, {
                  beat_tightness: Math.min(1000, Math.max(1, Number(e.target.value) || 200)),
                })
              }
            />
          </Field>
          <p className="text-[10px] text-muted-foreground">{t('sound_analyzer_default_hint')}</p>
        </div>
      ) : null}
    </div>
  )
}

function Field({
  label,
  value,
  children,
}: {
  label: string
  value?: string
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground">{label}</span>
      {children ?? <span className="text-foreground">{value}</span>}
    </div>
  )
}
