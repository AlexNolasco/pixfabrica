import { apiFetch } from '@/lib/apiClient'
import { mediaSourceApiPath } from '@/lib/mediaSourcePath'

/** Raw PCM (Float32) memory budget for the decoded-audio cache. */
const MAX_CACHE_BYTES = 300 * 1024 * 1024

interface CacheEntry {
  pending: Promise<AudioBuffer>
  bytes: number
}

// Map iteration order is insertion order; re-inserting on access turns this into an LRU.
const bufferCache = new Map<string, CacheEntry>()
let cacheBytes = 0

function audioBufferBytes(buf: AudioBuffer): number {
  return buf.length * buf.numberOfChannels * 4
}

function touch(key: string, entry: CacheEntry): void {
  bufferCache.delete(key)
  bufferCache.set(key, entry)
}

function evictToFit(incomingBytes: number, protectedKey: string): void {
  for (const [key, entry] of bufferCache) {
    if (cacheBytes + incomingBytes <= MAX_CACHE_BYTES) break
    if (key === protectedKey) continue
    bufferCache.delete(key)
    cacheBytes -= entry.bytes
  }
}

let sharedContext: AudioContext | null = null

export function getSharedAudioContext(): AudioContext {
  if (!sharedContext) {
    sharedContext = new AudioContext()
  }
  return sharedContext
}

async function decodeSource(source: string): Promise<AudioBuffer> {
  const fetchPath = mediaSourceApiPath(source)
  const res = await apiFetch(fetchPath)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const raw = await res.arrayBuffer()
  const ctx = getSharedAudioContext()
  return ctx.decodeAudioData(raw.slice(0))
}

/** Decode once per source URL; shared by waveform peaks and timeline playback. */
export async function fetchAudioBuffer(source: string): Promise<AudioBuffer | null> {
  const key = source.trim()
  if (!key) return null

  let entry = bufferCache.get(key)
  if (!entry) {
    const pending = decodeSource(key)
    entry = { pending, bytes: 0 }
    bufferCache.set(key, entry)
    void pending
      .then((buf) => {
        const bytes = audioBufferBytes(buf)
        entry!.bytes = bytes
        cacheBytes += bytes
        evictToFit(bytes, key)
      })
      .catch(() => {})
  } else {
    touch(key, entry)
  }
  try {
    return await entry.pending
  } catch {
    if (bufferCache.get(key) === entry) {
      bufferCache.delete(key)
      cacheBytes -= entry.bytes
    }
    return null
  }
}

/** Warm the decode cache after upload or source change. */
export function prefetchAudioBuffer(source: string): void {
  const key = source.trim()
  if (!key) return
  void fetchAudioBuffer(key).catch(() => {})
}

export function invalidateAudioBuffer(source: string): void {
  const key = source.trim()
  const entry = bufferCache.get(key)
  if (!entry) return
  bufferCache.delete(key)
  cacheBytes -= entry.bytes
}

export function clearAudioBufferCache(): void {
  bufferCache.clear()
  cacheBytes = 0
}
