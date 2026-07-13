import { create } from 'zustand'

export type ToastVariant = 'info' | 'warn' | 'error'

export interface ToastEntry {
  id: string
  message: string
  variant: ToastVariant
}

interface ToastState {
  toasts: ToastEntry[]
  pushToast: (message: string, variant?: ToastVariant) => void
  dismissToast: (id: string) => void
}

const AUTO_DISMISS_MS = 6000

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  pushToast: (message, variant = 'info') => {
    const id = crypto.randomUUID()
    set((s) => ({ toasts: [...s.toasts, { id, message, variant }] }))
    window.setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, AUTO_DISMISS_MS)
  },
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))
