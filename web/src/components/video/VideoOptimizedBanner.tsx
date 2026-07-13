import { useEffect, useState } from 'react'
import { fetchUploadManifest, mediaFilenameFromSource } from '@/lib/mediaUpload'
import { useT } from '@/lib/i18n'
import { useProjectStore } from '@/store/projectStore'

export function VideoOptimizedBanner({ source }: { source: string }) {
  const t = useT()
  const projectWidth = useProjectStore((s) => s.meta.width)
  const projectHeight = useProjectStore((s) => s.meta.height)
  const [optimizedFor, setOptimizedFor] = useState<{
    width: number
    height: number
  } | null>(null)

  useEffect(() => {
    let active = true
    const filename = mediaFilenameFromSource(source)
    if (!filename) {
      setOptimizedFor(null)
      return () => {
        active = false
      }
    }

    void fetchUploadManifest(filename).then((manifest) => {
      if (!active) return
      const raw = manifest?.optimized_for
      if (!raw) {
        setOptimizedFor(null)
        return
      }
      setOptimizedFor({ width: raw.width, height: raw.height })
    })

    return () => {
      active = false
    }
  }, [source])

  if (
    optimizedFor == null
    || projectWidth <= optimizedFor.width
    && projectHeight <= optimizedFor.height
  ) {
    return null
  }

  return (
    <p className="text-[10px] text-amber-600 dark:text-amber-400 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 leading-snug">
      {t('prop_video_resolution_mismatch')
        .replace('{width}', String(optimizedFor.width))
        .replace('{height}', String(optimizedFor.height))}
    </p>
  )
}
