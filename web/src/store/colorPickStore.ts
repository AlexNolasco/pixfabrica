import { create } from 'zustand'

interface ColorPickState {
  active: boolean
  onPick: ((hex: string) => void) | null
  beginPick: (onPick: (hex: string) => void) => void
  cancelPick: () => void
  completePick: (hex: string) => void
}

export const useColorPickStore = create<ColorPickState>((set, get) => ({
  active: false,
  onPick: null,
  beginPick: (onPick) => set({ active: true, onPick }),
  cancelPick: () => set({ active: false, onPick: null }),
  completePick: (hex) => {
    const cb = get().onPick
    set({ active: false, onPick: null })
    cb?.(hex)
  },
}))
