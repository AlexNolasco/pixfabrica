import { timelineAudioEngine } from '@/lib/timelineAudioEngine'
import { useProjectStore } from '@/store/projectStore'

/** Pause timeline transport in place when API preview is unavailable. */
export function stopPlaybackOnApiLoss(): void {
  const state = useProjectStore.getState()
  if (state.isPlaying) {
    state.setIsPlaying(false)
  }
  timelineAudioEngine.stop()
}
