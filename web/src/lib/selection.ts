/** Timeline / properties selection for a placed clip. */
export type ClipSelection = {
  kind: 'clip'
  trackId: string
  clipId: string
}

export function isClipSelection(
  selection: { kind: string } | null | undefined,
): selection is ClipSelection {
  return selection?.kind === 'clip'
}
