/** Enable in devtools: localStorage.setItem('pixfabrica:preview-debug', '1') */
export function previewDebug(message: string, data?: Record<string, unknown>): void {
  if (typeof localStorage === 'undefined') return
  if (localStorage.getItem('pixfabrica:preview-debug') !== '1') return
  if (data) {
    console.debug(`[preview] ${message}`, data)
  } else {
    console.debug(`[preview] ${message}`)
  }
}
