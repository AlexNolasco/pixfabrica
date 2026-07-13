import { fetchAudioBuffer, getSharedAudioContext } from '@/lib/audioBufferCache'
import { effectiveSoundEnabled, type Sound } from '@/lib/sound'
import type { ProjectMeta } from '@/store/projectStore'
import { resolvedSoundDuration } from '@/store/projectStore'

export interface TimelineAudioStartOptions {
  timelineT: number
  projectDuration: number
  sounds: Sound[]
  meta: ProjectMeta
  muted: boolean
}

type ActiveSource = {
  source: AudioBufferSourceNode
  gain: GainNode
}

class TimelineAudioEngine {
  private sources: ActiveSource[] = []
  private masterGain: GainNode | null = null
  private limiter: DynamicsCompressorNode | null = null
  private generation = 0

  async start(opts: TimelineAudioStartOptions): Promise<void> {
    const gen = ++this.generation
    this.stopInternal()
    const { timelineT, projectDuration, sounds, meta, muted } = opts
    if (projectDuration <= 0) return

    const ctx = getSharedAudioContext()
    if (ctx.state === 'suspended') {
      await ctx.resume()
    }

    const master = this.ensureOutputChain(ctx)
    master.gain.value = muted ? 0 : 1

    const baseWhen = ctx.currentTime + 0.02

    for (const sound of sounds) {
      if (!effectiveSoundEnabled(sound)) continue

      const spanDur = resolvedSoundDuration(sound, meta)
      const spanStart = sound.start
      const spanEnd = sound.start + spanDur
      if (timelineT >= spanEnd) continue

      const buffer = await fetchAudioBuffer(sound.source)
      if (gen !== this.generation) return
      if (!buffer) continue

      const fileOffset = sound.seek + Math.max(0, timelineT - spanStart)
      if (fileOffset >= buffer.duration) continue

      const bufferRemaining = buffer.duration - fileOffset
      const spanRemaining = spanEnd - Math.max(timelineT, spanStart)
      const projectRemaining = projectDuration - timelineT
      const playDuration = Math.min(bufferRemaining, spanRemaining, projectRemaining)
      if (playDuration <= 0) continue

      const delay = Math.max(0, spanStart - timelineT)
      const when = baseWhen + delay

      const source = ctx.createBufferSource()
      source.buffer = buffer
      const gain = ctx.createGain()
      gain.gain.value = sound.volume
      source.connect(gain)
      gain.connect(master)
      source.start(when, fileOffset, playDuration)
      this.sources.push({ source, gain })
    }
  }

  setMuted(muted: boolean): void {
    if (this.masterGain) {
      this.masterGain.gain.value = muted ? 0 : 1
    }
  }

  stop(): void {
    this.generation += 1
    this.stopInternal()
  }

  private ensureOutputChain(ctx: AudioContext): GainNode {
    if (this.masterGain && this.limiter) {
      return this.masterGain
    }

    const master = ctx.createGain()
    const limiter = ctx.createDynamicsCompressor()
    limiter.threshold.value = -3
    limiter.knee.value = 12
    limiter.ratio.value = 8
    limiter.attack.value = 0.003
    limiter.release.value = 0.15
    master.connect(limiter)
    limiter.connect(ctx.destination)
    this.masterGain = master
    this.limiter = limiter
    return master
  }

  private stopInternal(): void {
    for (const { source, gain } of this.sources) {
      try {
        source.stop()
      } catch {
        // already stopped
      }
      source.disconnect()
      gain.disconnect()
    }
    this.sources = []
  }
}

export const timelineAudioEngine = new TimelineAudioEngine()
