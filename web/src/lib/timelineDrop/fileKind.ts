export function fileExtension(name: string): string {
  const base = name.replace(/\\/g, '/').split('/').pop() ?? name
  const dot = base.lastIndexOf('.')
  return dot >= 0 ? base.slice(dot).toLowerCase() : ''
}
