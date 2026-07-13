import { create } from 'zustand'
import type { MediaUploadContext } from '@/lib/mediaUpload'

export type StockParamApplyResult = {
  path: string
  extraParams: Record<string, string>
}

export type StockParamTarget = {
  uploadContext: MediaUploadContext
  field: string
  onApply: (result: StockParamApplyResult) => void
}

type PhotoContext =
  | { mode: 'menu' }
  | { mode: 'param'; target: StockParamTarget }

type VideoContext =
  | { mode: 'menu' }
  | { mode: 'param'; target: StockParamTarget }

interface StockPickerState {
  photosOpen: boolean
  videosOpen: boolean
  photoContext: PhotoContext
  videoContext: VideoContext
  openMenuPhotos: () => void
  openMenuVideos: () => void
  openParamPhotos: (target: StockParamTarget) => void
  openParamVideos: (target: StockParamTarget) => void
  closePhotos: () => void
  closeVideos: () => void
  closeAll: () => void
}

export const useStockPickerStore = create<StockPickerState>((set) => ({
  photosOpen: false,
  videosOpen: false,
  photoContext: { mode: 'menu' },
  videoContext: { mode: 'menu' },
  openMenuPhotos: () => set({ photosOpen: true, photoContext: { mode: 'menu' } }),
  openMenuVideos: () => set({ videosOpen: true, videoContext: { mode: 'menu' } }),
  openParamPhotos: (target) =>
    set({ photosOpen: true, photoContext: { mode: 'param', target } }),
  openParamVideos: (target) =>
    set({ videosOpen: true, videoContext: { mode: 'param', target } }),
  closePhotos: () => set({ photosOpen: false, photoContext: { mode: 'menu' } }),
  closeVideos: () => set({ videosOpen: false, videoContext: { mode: 'menu' } }),
  closeAll: () =>
    set({
      photosOpen: false,
      videosOpen: false,
      photoContext: { mode: 'menu' },
      videoContext: { mode: 'menu' },
    }),
}))
