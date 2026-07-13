import { useCallback, useEffect, useRef, useState } from 'react'

const inputClass =
  'w-full rounded border border-border bg-background px-2 py-1 text-xs font-mono outline-none focus:border-primary/60'

export function ParamNumber({
  value,
  step,
  debounceMs = 200,
  onCommit,
}: {
  value: number
  step: number
  debounceMs?: number
  onCommit: (v: number) => void
}) {
  const format = (n: number) => (Number.isFinite(n) ? String(n) : '0')
  const draftRef = useRef(format(value))
  const [draft, setDraft] = useState(format(value))
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
      setDraftValue(format(value))
    }
  }, [value, setDraftValue])

  const commitDraft = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = undefined
    }
    const parsed = Number(draftRef.current)
    if (!Number.isFinite(parsed) || parsed === lastCommittedRef.current) return
    lastCommittedRef.current = parsed
    onCommit(parsed)
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
      const parsed = Number(draftRef.current)
      if (
        Number.isFinite(parsed) &&
        parsed !== lastCommittedRef.current
      ) {
        lastCommittedRef.current = parsed
        onCommitRef.current(parsed)
      }
    },
    [],
  )

  return (
    <input
      type="number"
      className={inputClass}
      value={draft}
      step={step}
      onFocus={() => {
        editingRef.current = true
      }}
      onBlur={() => {
        editingRef.current = false
        commitDraft()
      }}
      onChange={(e) => {
        setDraftValue(e.target.value)
        scheduleCommit()
      }}
    />
  )
}
