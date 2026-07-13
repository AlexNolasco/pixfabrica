import { effectiveAnalyzerForPreview } from '@/lib/effectiveAnalyzer'
import type { AudioAnalyzeJobState } from '@/lib/audioAnalysis'
import { toRenderJob, type RenderJobJson } from '@/lib/renderJob'
import type { Sound } from '@/lib/sound'
import type { ProjectSetting, ProjectMeta, Track } from '@/store/projectStore'
import type { JobColorPalette, PaletteSource } from '@/lib/jobColors'
import type { FontPalette } from '@/lib/typography'
import type { ClipCatalogDetail } from '@/lib/catalogDetail'

export function toPreviewRenderJob(
  state: {
    meta: ProjectMeta
    tracks: Track[]
    sounds: Sound[]
    projectSettings: ProjectSetting[]
    typography: FontPalette
    colors: JobColorPalette
    paletteSource: PaletteSource
    locale?: string
    description?: string
    catalogDetailCache?: Record<string, ClipCatalogDetail>
  },
  analysisBySoundId: Record<string, AudioAnalyzeJobState | undefined>,
): RenderJobJson {
  const job = toRenderJob(state)
  return {
    ...job,
    sounds: (job.sounds ?? []).map((entry) => {
      const sound = state.sounds.find((s) => s.id === entry.id)
      if (!sound) return entry
      return {
        ...entry,
        analyzer: effectiveAnalyzerForPreview(
          sound,
          state.meta.fps,
          analysisBySoundId[sound.id],
        ),
      }
    }),
  }
}
