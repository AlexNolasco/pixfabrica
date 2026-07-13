/** Filename without path or extension, for track labels. */
export function fileStem(filename: string): string {
  const base = filename.replace(/\\/g, '/').split('/').pop() ?? filename
  const dot = base.lastIndexOf('.')
  return dot > 0 ? base.slice(0, dot) : base
}
