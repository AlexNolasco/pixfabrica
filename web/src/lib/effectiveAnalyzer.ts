import type { Sound } from '@/lib/sound'
import { DEFAULT_ANALYZER } from '@/lib/sound'

/** Single StemAnalyzer backend — no preview downgrade. */
export function effectiveAnalyzerForPreview(
  _sound: Sound,
  _fps: number,
  _job: unknown,
): typeof DEFAULT_ANALYZER {
  return DEFAULT_ANALYZER
}
