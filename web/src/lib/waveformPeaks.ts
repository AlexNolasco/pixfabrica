import { fetchAudioBuffer } from '@/lib/audioBufferCache'

/** Entry count budget; each entry is a small downsampled array, so a count cap is enough. */
const MAX_CACHE_ENTRIES = 1000

// Map iteration order is insertion order; re-inserting on access turns this into an LRU.
const peaksCache = new Map<string, number[]>()

const FALLBACK_PEAKS = Array.from({ length: 80 }, () => 0.12)

function touch(key: string, peaks: number[]): void {
  peaksCache.delete(key)
  peaksCache.set(key, peaks)
}

function evictOverflow(): void {
  for (const key of peaksCache.keys()) {
    if (peaksCache.size <= MAX_CACHE_ENTRIES) break
    peaksCache.delete(key)
  }
}

function downsamplePeaks(channelData: Float32Array, targetCount: number): number[] {
  const blockSize = Math.max(1, Math.floor(channelData.length / targetCount))
  const peaks: number[] = []
  for (let i = 0; i < targetCount; i++) {
    const start = i * blockSize
    const end = Math.min(channelData.length, start + blockSize)
    let max = 0
    for (let j = start; j < end; j++) {
      const v = Math.abs(channelData[j] ?? 0)
      if (v > max) max = v
    }
    peaks.push(max)
  }
  const peakMax = Math.max(...peaks, 1e-6)
  return peaks.map((v) => v / peakMax)
}

export async function fetchWaveformPeaks(
  source: string,
  targetCount = 96,
): Promise<number[]> {
  const key = source.trim()
  if (!key) return FALLBACK_PEAKS

  const cached = peaksCache.get(key)
  if (cached) {
    touch(key, cached)
    return cached
  }

  try {
    const audio = await fetchAudioBuffer(key)
    if (!audio) throw new Error('decode failed')
    const channel = audio.getChannelData(0)
    const peaks = downsamplePeaks(channel, targetCount)
    peaksCache.set(key, peaks)
    evictOverflow()
    return peaks
  } catch {
    return FALLBACK_PEAKS
  }
}

export function clearWaveformPeaksCache(): void {
  peaksCache.clear()
}
