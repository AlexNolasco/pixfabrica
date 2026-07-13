/** Marks a panel where timeline transport keys (Space, Enter, Home) are suppressed. */
export const TRANSPORT_BLOCK_ATTR = 'data-transport-block'

export function isTransportKeyboardBlocked(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false

  const tag = target.tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || target.isContentEditable) return true

  if (target.closest('[data-slot="slider"]')) return true
  if (target.closest('[role="listbox"]')) return true
  if (target.closest('[role="menu"]')) return true
  if (target.closest(`[${TRANSPORT_BLOCK_ATTR}]`)) return true

  return false
}
