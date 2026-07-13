import { useCallback, useEffect, useRef, useState } from 'react'

const inputClass =
  'w-full rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60'

export function ParamText({
  value,
  multiline,
  rows = 4,
  debounceMs = 200,
  readOnly = false,
  onCommit,
}: {
  value: string
  multiline?: boolean
  rows?: number
  debounceMs?: number
  readOnly?: boolean
  onCommit: (v: string) => void
}) {
  const draftRef = useRef(value)
  const [draft, setDraft] = useState(value)
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

  const commitDraft = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = undefined
    }
    if (draftRef.current === lastCommittedRef.current) return
    lastCommittedRef.current = draftRef.current
    onCommit(draftRef.current)
  }, [onCommit])

  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit

  const scheduleCommit = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      timerRef.current = undefined
      commitDraft()
    }, debounceMs)
  }, [commitDraft, debounceMs])

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (draftRef.current !== lastCommittedRef.current) {
        lastCommittedRef.current = draftRef.current
        onCommitRef.current(draftRef.current)
      }
    },
    [],
  )

  const handleChange = (next: string) => {
    setDraftValue(next)
    scheduleCommit()
  }

  const handleFocus = () => {
    editingRef.current = true
  }

  const handleBlur = () => {
    editingRef.current = false
    commitDraft()
  }

  if (multiline) {
    return (
      <textarea
        className={`${inputClass} min-h-[4rem] resize-y${readOnly ? ' cursor-default opacity-90' : ''}`}
        rows={rows}
        value={draft}
        readOnly={readOnly}
        onFocus={readOnly ? undefined : handleFocus}
        onBlur={readOnly ? undefined : handleBlur}
        onChange={readOnly ? undefined : (e) => handleChange(e.target.value)}
      />
    )
  }

  return (
    <input
      type="text"
      className={inputClass}
      value={draft}
      readOnly={readOnly}
      onFocus={readOnly ? undefined : handleFocus}
      onBlur={readOnly ? undefined : handleBlur}
      onChange={readOnly ? undefined : (e) => handleChange(e.target.value)}
    />
  )
}
