import { Loader2, MessageSquare, Sparkles, X } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { apiComposeChat, apiDeleteComposeSession } from '@/lib/composeApi'
import { ApiHttpError } from '@/lib/apiClient'
import { useT } from '@/lib/i18n'
import type { TranslationKey } from '@/lib/i18n'
import { executeProjectImport, parseProjectJsonValue } from '@/lib/projectFileActions'
import { useProjectStore } from '@/store/projectStore'

function composeUnavailableKey(reason: string | null): TranslationKey {
  switch (reason) {
    case 'model_not_installed':
      return 'compose_unavailable_model'
    case 'tools_not_supported':
      return 'compose_unavailable_tools'
    case 'tools_capability_unknown':
      return 'compose_unavailable_tools_unknown'
    case 'invalid_tags_response':
      return 'compose_unavailable_invalid'
    default:
      return 'compose_unavailable_ollama'
  }
}

function tryApplyComposeProject(
  project: Record<string, unknown>,
  t: (key: TranslationKey) => string,
  appendEventLog: (level: 'info' | 'warn' | 'error', message: string) => void,
  logKey: TranslationKey = 'compose_auto_loaded',
): boolean {
  const parsed = parseProjectJsonValue(project, 'compose.json')
  if (!parsed.ok) {
    appendEventLog('warn', t('compose_load_invalid'))
    return false
  }
  executeProjectImport(parsed.payload)
  appendEventLog('info', t(logKey))
  return true
}

export function ComposePanel() {
  const t = useT()
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const composeHealth = useProjectStore((s) => s.composeHealth)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const closeComposePanel = useProjectStore((s) => s.closeComposePanel)
  const clearComposeChat = useProjectStore((s) => s.clearComposeChat)
  const sessionId = useProjectStore((s) => s.composeSessionId)
  const messages = useProjectStore((s) => s.composeMessages)
  const lastProject = useProjectStore((s) => s.composeLastProject)
  const colors = useProjectStore((s) => s.colors)
  const paletteSource = useProjectStore((s) => s.paletteSource)
  const setComposeSessionId = useProjectStore((s) => s.setComposeSessionId)
  const appendComposeMessages = useProjectStore((s) => s.appendComposeMessages)
  const setComposeLastProject = useProjectStore((s) => s.setComposeLastProject)

  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [autoLoad, setAutoLoad] = useState(true)
  const listRef = useRef<HTMLDivElement>(null)
  const msgId = useRef(0)

  const apiOffline = apiConnectionStatus !== 'connected'
  const composeReady = composeHealth?.ready === true && !apiOffline

  const unavailableMessage = (() => {
    if (apiOffline) return t('compose_unavailable_api')
    if (!composeHealth) return t('compose_unavailable_checking')
    if (composeHealth.ready) return null
    const key = composeUnavailableKey(composeHealth.reason)
    return t(key).replace('{model}', composeHealth.model)
  })()

  const scrollToBottom = useCallback(() => {
    const el = listRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [])

  const handleLoadProject = useCallback(() => {
    if (!lastProject) return
    tryApplyComposeProject(lastProject, t, appendEventLog, 'compose_load_success')
  }, [appendEventLog, lastProject, t])

  const handleSend = useCallback(async () => {
    const text = draft.trim()
    if (!text || pending || !composeReady) return

    appendComposeMessages([{ id: `msg-${++msgId.current}`, role: 'user', content: text }])
    setDraft('')
    setPending(true)
    requestAnimationFrame(scrollToBottom)

    try {
      const res = await apiComposeChat({
        session_id: sessionId ?? undefined,
        message: text,
        job_context: {
          colors,
          palette_source: paletteSource,
        },
      })
      setComposeSessionId(res.session_id)

      let assistantText = res.assistant_message
      if (res.project && typeof res.project === 'object') {
        setComposeLastProject(res.project)
        if (autoLoad) {
          if (tryApplyComposeProject(res.project, t, appendEventLog)) {
            assistantText = `${assistantText}\n\n${t('compose_auto_loaded_inline')}`
          }
        } else {
          assistantText = `${assistantText}\n\n${t('compose_ready_to_load_inline')}`
        }
      }

      appendComposeMessages([
        {
          id: `msg-${++msgId.current}`,
          role: 'assistant',
          content: assistantText,
        },
      ])
    } catch (err) {
      const detail =
        err instanceof ApiHttpError
          ? err.detail ?? err.message
          : err instanceof Error
            ? err.message
            : t('compose_send_failed')
      appendComposeMessages([
        { id: `msg-${++msgId.current}`, role: 'assistant', content: detail },
      ])
      appendEventLog('error', `${t('compose_send_failed')}: ${detail}`)
    } finally {
      setPending(false)
      requestAnimationFrame(scrollToBottom)
    }
  }, [
    appendComposeMessages,
    appendEventLog,
    autoLoad,
    colors,
    composeReady,
    draft,
    paletteSource,
    pending,
    scrollToBottom,
    sessionId,
    setComposeLastProject,
    setComposeSessionId,
    t,
  ])

  const handleNewChat = useCallback(() => {
    const previousSessionId = sessionId
    clearComposeChat()
    if (previousSessionId) {
      void apiDeleteComposeSession(previousSessionId).catch(() => {
        // Local UI is already cleared; server session will age out on restart if delete fails.
      })
    }
  }, [clearComposeChat, sessionId])

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0 text-xs">
      <header className="flex items-center justify-between gap-2 border-b border-border px-3 py-2 shrink-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <Sparkles className="w-3.5 h-3.5 shrink-0 text-primary" />
          <h2 className="text-[11px] font-semibold uppercase tracking-wider truncate">
            {t('compose_title')}
          </h2>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-[10px]"
            onClick={handleNewChat}
            disabled={pending || messages.length === 0}
          >
            {t('compose_new_chat')}
          </Button>
          <button
            type="button"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={closeComposePanel}
            aria-label={t('compose_close')}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </header>

      <div className="flex flex-col flex-1 min-h-0 px-3 py-3 gap-3">
        {!composeReady && unavailableMessage ? (
          <p className="text-[11px] text-muted-foreground leading-snug rounded border border-border/60 bg-muted/20 px-2 py-2 shrink-0">
            {unavailableMessage}
          </p>
        ) : (
          <p className="text-[11px] text-muted-foreground leading-snug shrink-0">
            {t('compose_hint')}
          </p>
        )}

        <div
          ref={listRef}
          className="flex flex-col gap-2 flex-1 min-h-0 overflow-y-auto rounded border border-border/60 bg-muted/15 px-2 py-2"
        >
          {messages.length === 0 ? (
            <p className="text-muted-foreground italic text-[11px] leading-snug m-auto text-center px-4">
              {t('compose_empty')}
            </p>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`text-[12px] leading-relaxed rounded px-2.5 py-2 whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-primary/15 text-foreground ml-6'
                    : 'bg-muted/40 text-foreground mr-4'
                }`}
              >
                {msg.content}
              </div>
            ))
          )}
          {pending ? (
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground px-1">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {t('compose_thinking')}
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-2 shrink-0">
          <label className="flex items-center gap-2 text-[11px] text-muted-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              className="rounded border-border"
              checked={autoLoad}
              disabled={pending}
              onChange={(e) => setAutoLoad(e.target.checked)}
            />
            {t('compose_auto_load')}
          </label>
          {!autoLoad && lastProject && !pending ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 text-xs w-full"
              onClick={handleLoadProject}
            >
              {t('compose_load_project')}
            </Button>
          ) : null}
          <textarea
            rows={3}
            disabled={!composeReady || pending}
            placeholder={composeReady ? t('compose_placeholder') : t('compose_placeholder_disabled')}
            className="w-full resize-none rounded border border-border bg-muted/50 px-2.5 py-2 text-xs text-foreground outline-none focus:border-primary/60 disabled:opacity-50"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <Button
            type="button"
            size="sm"
            className="h-8 text-xs w-full"
            disabled={!composeReady || pending || !draft.trim()}
            onClick={() => void handleSend()}
          >
            <MessageSquare className="w-3.5 h-3.5 mr-1.5" />
            {t('compose_send')}
          </Button>
        </div>
      </div>
    </div>
  )
}
