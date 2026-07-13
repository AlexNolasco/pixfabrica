import { useCallback, useEffect, useRef, useState } from 'react'
import {
  acceptAttribute,
  apiIngestMediaUrl,
  apiUploadMedia,
  formatMaxBytes,
  isRemoteMediaUrl,
  projectUploadTarget,
  type MediaUploadContext,
} from '@/lib/mediaUpload'
import { useT } from '@/lib/i18n'

const inputClass =
  'min-w-0 flex-1 rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60'

export function ParamFile({
  value,
  fieldName = 'source',
  uploadKind,
  uploadContext,
  accept,
  maxBytes,
  nullable,
  stockBrowse,
  onOpenStockBrowse,
  onCommit,
}: {
  value: string
  fieldName?: string
  uploadKind: string
  uploadContext: MediaUploadContext
  accept: string[]
  maxBytes: number
  nullable?: boolean
  stockBrowse?: boolean
  onOpenStockBrowse?: () => void
  onCommit: (v: string) => void
}) {
  const t = useT()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const draftRef = useRef(value)
  const [draft, setDraft] = useState(value)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const editingRef = useRef(false)
  const lastCommittedRef = useRef(value)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const setDraftValue = useCallback((v: string) => {
    draftRef.current = v
    setDraft(v)
  }, [])

  useEffect(() => {
    lastCommittedRef.current = value
    if (!editingRef.current) {
      setDraftValue(value)
    }
  }, [value, setDraftValue])

  const commitDraft = useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = undefined
    }
    const draft = draftRef.current
    if (draft === lastCommittedRef.current) return

    if (
      isRemoteMediaUrl(draft)
      && uploadKind === 'image'
      && uploadContext
    ) {
      setError(null)
      setUploading(true)
      try {
        const target = projectUploadTarget()
        const res = await apiIngestMediaUrl(
          draft,
          uploadKind,
          uploadContext,
          target,
          fieldName,
        )
        editingRef.current = false
        setDraftValue(res.path)
        lastCommittedRef.current = res.path
        onCommit(res.path)
      } catch (e) {
        setError(e instanceof Error ? e.message : t('param_file_upload_failed'))
      } finally {
        setUploading(false)
      }
      return
    }

    lastCommittedRef.current = draft
    onCommit(draft)
  }, [fieldName, onCommit, t, uploadContext, uploadKind])

  const scheduleCommit = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      timerRef.current = undefined
      void commitDraft()
    }, 200)
  }, [commitDraft])

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  const handleBrowse = async (file: File | undefined) => {
    if (!file) return
    setError(null)
    if (file.size > maxBytes) {
      setError(`${t('param_file_too_large')} (${formatMaxBytes(maxBytes)})`)
      return
    }
    setUploading(true)
    try {
      const target =
        uploadContext && (uploadKind === 'video' || uploadKind === 'image')
          ? projectUploadTarget()
          : undefined
      const res = await apiUploadMedia(file, uploadKind, uploadContext, target)
      editingRef.current = false
      setDraftValue(res.path)
      lastCommittedRef.current = res.path
      onCommit(res.path)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('param_file_upload_failed'))
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleClear = () => {
    editingRef.current = false
    setDraftValue('')
    lastCommittedRef.current = ''
    onCommit('')
    setError(null)
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <input
          type="text"
          className={inputClass}
          value={draft}
          placeholder={t('param_file_placeholder')}
          onFocus={() => {
            editingRef.current = true
          }}
          onBlur={() => {
            editingRef.current = false
            void commitDraft()
          }}
          onChange={(e) => {
            setDraftValue(e.target.value)
            scheduleCommit()
          }}
        />
        <button
          type="button"
          disabled={uploading}
          className="shrink-0 rounded border border-border bg-muted/60 px-2 py-1 text-[10px] text-foreground hover:bg-muted disabled:opacity-50"
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading
            ? uploadKind === 'video'
              ? t('param_file_optimizing_video')
              : t('param_file_uploading')
            : t('param_file_browse')}
        </button>
        {stockBrowse && onOpenStockBrowse ? (
          <button
            type="button"
            disabled={uploading}
            className="shrink-0 rounded border border-border bg-muted/60 px-2 py-1 text-[10px] text-foreground hover:bg-muted disabled:opacity-50"
            onClick={onOpenStockBrowse}
          >
            {t('param_file_browse_stock')}
          </button>
        ) : null}
        {nullable ? (
          <button
            type="button"
            disabled={uploading}
            className="shrink-0 rounded border border-border bg-muted/60 px-2 py-1 text-[10px] text-muted-foreground hover:bg-muted disabled:opacity-50"
            onClick={handleClear}
          >
            {t('param_file_clear')}
          </button>
        ) : null}
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept={accept.length > 0 ? acceptAttribute(accept) : undefined}
          onChange={(e) => void handleBrowse(e.target.files?.[0])}
        />
      </div>
      <p className="text-[10px] text-muted-foreground">
        {t('param_file_hint')} {formatMaxBytes(maxBytes)}.
      </p>
      {error ? <p className="text-[10px] text-destructive">{error}</p> : null}
    </div>
  )
}
