import type { TranslationKey } from '@/lib/i18n'
import type { CatalogClipItem, CatalogTrackKind } from '@/store/projectStore'

export type CatalogViewMode = 'list' | 'icons'

const CATEGORY_ORDER: string[] = [
  'background',
  'particles',
  'effects',
  'text',
  'image',
  'video',
  'mesh',
  'lyrics',
  'progress',
  'player',
  'postprocess',
  'utility',
  'math',
  'logic',
  'audio',
  'track',
  'theme_generator',
]

export function readCatalogViewMode(): CatalogViewMode {
  try {
    const raw = localStorage.getItem('catalog:viewMode')
    return raw === 'icons' ? 'icons' : 'list'
  } catch {
    return 'list'
  }
}

export function writeCatalogViewMode(mode: CatalogViewMode): void {
  localStorage.setItem('catalog:viewMode', mode === 'icons' ? 'icons' : 'list')
}

export function categoryTranslationKey(category: string): TranslationKey {
  return `category.${category}` as TranslationKey
}

export function tagTranslationKey(tag: string): TranslationKey {
  return `tag.${tag}` as TranslationKey
}

function compareLabels(a: CatalogClipItem, b: CatalogClipItem): number {
  return a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })
}

function nodeMatchesSearch(
  node: CatalogClipItem,
  query: string,
  tagLabels: string[],
): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  if (node.label.toLowerCase().includes(q)) return true
  if (node.description.toLowerCase().includes(q)) return true
  if (node.clip_type.toLowerCase().includes(q)) return true
  if (node.tags.some((t) => t.toLowerCase().includes(q))) return true
  if (tagLabels.some((l) => l.toLowerCase().includes(q))) return true
  return false
}

export type CatalogSection = {
  category: string
  clips: CatalogClipItem[]
}

export function buildCatalogDisplay(
  clips: CatalogClipItem[],
  trackKind: CatalogTrackKind,
  searchQuery: string,
  resolveTagLabel: (tag: string) => string,
): { flat: CatalogClipItem[]; sections: CatalogSection[] } {
  const filtered = clips
    .filter((n) => n.track_kind === trackKind)
    .filter((n) => !n.disabled)
    .filter((n) =>
      nodeMatchesSearch(
        n,
        searchQuery,
        n.tags.map((t) => resolveTagLabel(t)),
      ),
    )

  const pinned = filtered.filter((n) => n.pinned).sort(compareLabels)
  const unpinned = filtered.filter((n) => !n.pinned)

  const sortNodes = (list: CatalogClipItem[]) => [...list].sort(compareLabels)

  const q = searchQuery.trim()
  if (q) {
    const flat = [...sortNodes(pinned), ...sortNodes(unpinned)]
    return { flat, sections: [{ category: '', clips: flat }] }
  }

  const byCategory = new Map<string, CatalogClipItem[]>()
  for (const node of unpinned) {
    const bucket = byCategory.get(node.category) ?? []
    bucket.push(node)
    byCategory.set(node.category, bucket)
  }

  const sections: CatalogSection[] = []
  if (pinned.length > 0) {
    sections.push({ category: '__pinned__', clips: sortNodes(pinned) })
  }

  const orderedCategories = [
    ...CATEGORY_ORDER.filter((c) => byCategory.has(c)),
    ...[...byCategory.keys()].filter((c) => !CATEGORY_ORDER.includes(c)).sort(),
  ]

  for (const category of orderedCategories) {
    const catNodes = byCategory.get(category)
    if (catNodes?.length) {
      sections.push({ category, clips: sortNodes(catNodes) })
    }
  }

  const flat: CatalogClipItem[] = []
  for (const section of sections) {
    flat.push(...section.clips)
  }
  return { flat, sections }
}

export function catalogKindForTrack(
  trackType: 'skia' | 'gl' | 'audio' | 'post' | undefined,
): CatalogTrackKind {
  return trackType === 'gl' || trackType === 'post' ? trackType : 'skia'
}

export function trackAcceptsCatalogClips(
  trackType: 'skia' | 'gl' | 'audio' | 'post' | undefined,
  enabled: boolean,
): boolean {
  if (!enabled) return false
  const type = trackType ?? 'skia'
  return type === 'skia' || type === 'gl' || type === 'post'
}
