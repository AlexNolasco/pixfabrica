export type ClipPreviewAudioOptions = {
  /** Baked sample id from manifest.json; null = API legacy demo snippet. */
  sampleId: string | null
  busMuted: boolean
}

let options: ClipPreviewAudioOptions = { sampleId: null, busMuted: false }

export function setClipPreviewAudioOptions(next: ClipPreviewAudioOptions): void {
  options = next
}

export function getClipPreviewAudioOptions(): ClipPreviewAudioOptions {
  return options
}
