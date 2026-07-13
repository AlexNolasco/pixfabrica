import type { ProjectSetting } from '@/store/projectStore'
import type { Sound } from '@/lib/sound'
import { duplicateBusNames } from '@/lib/sound'

/** Bus names for ``bus_select`` controls (sound publishers + job sound clips). */
export function listAudioBusNames(
  sounds: Sound[],
  projectSettings: ProjectSetting[],
): string[] {
  const names = new Set<string>()
  for (const s of sounds) {
    const bus = s.bus.trim()
    if (bus) names.add(bus)
  }
  for (const jn of projectSettings) {
    const bus = jn.params.audio_bus
    if (typeof bus === 'string' && bus.trim()) {
      names.add(bus.trim())
    }
  }
  return [...names].sort((a, b) => a.localeCompare(b))
}

export { duplicateBusNames }
