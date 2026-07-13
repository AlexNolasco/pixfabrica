/** Map a screen click on a displayed canvas to #RRGGBB from canvas pixel data. */
export function samplePreviewCanvasColor(
  canvas: HTMLCanvasElement,
  clientX: number,
  clientY: number,
): string | null {
  if (canvas.width <= 0 || canvas.height <= 0) return null

  const rect = canvas.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return null

  const x = Math.floor(((clientX - rect.left) / rect.width) * canvas.width)
  const y = Math.floor(((clientY - rect.top) / rect.height) * canvas.height)
  if (x < 0 || y < 0 || x >= canvas.width || y >= canvas.height) return null

  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null

  const [r, g, b, a] = ctx.getImageData(x, y, 1, 1).data
  if (a < 16) return null

  const toHex = (v: number) => v.toString(16).padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}
