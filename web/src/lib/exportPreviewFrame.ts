const INVALID_FILENAME_CHARS = /[\\/:*?"<>|]/g

function safeFilenameBase(title: string): string {
  const trimmed = title.trim()
  const base = trimmed.length > 0 ? trimmed : 'untitled'
  const safe = base.replace(INVALID_FILENAME_CHARS, '').trim()
  return safe.length > 0 ? safe : 'untitled'
}

/** PNG filename for a scrubbed composition frame. */
export function previewFrameFilename(title: string, tSeconds: number): string {
  return `${safeFilenameBase(title)}-t${tSeconds.toFixed(1)}.png`
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('canvas toBlob failed'))
    }, 'image/png')
  })
}

export async function downloadPngFromCanvas(
  canvas: HTMLCanvasElement,
  filename: string,
): Promise<void> {
  const blob = await canvasToPngBlob(canvas)
  triggerDownload(blob, filename)
}

export async function downloadPngFromRgba(
  width: number,
  height: number,
  rgba: Uint8ClampedArray,
  filename: string,
): Promise<void> {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('2d context unavailable')
  const image = new ImageData(new Uint8ClampedArray(rgba), width, height)
  ctx.putImageData(image, 0, 0)
  await downloadPngFromCanvas(canvas, filename)
}
