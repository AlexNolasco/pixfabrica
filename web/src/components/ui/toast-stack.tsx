import { X } from 'lucide-react'
import { useToastStore } from '@/store/toastStore'

export function ToastStack() {
  const toasts = useToastStore((s) => s.toasts)
  const dismissToast = useToastStore((s) => s.dismissToast)

  if (toasts.length === 0) return null

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm"
      aria-live="polite"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-md border px-3 py-2 text-xs shadow-lg ${
            toast.variant === 'error'
              ? 'border-destructive/40 bg-destructive/10 text-destructive'
              : toast.variant === 'warn'
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-950 dark:text-amber-100'
                : 'border-border bg-popover text-foreground'
          }`}
        >
          <span className="flex-1 leading-snug">{toast.message}</span>
          <button
            type="button"
            className="shrink-0 text-muted-foreground hover:text-foreground"
            onClick={() => dismissToast(toast.id)}
            aria-label="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
