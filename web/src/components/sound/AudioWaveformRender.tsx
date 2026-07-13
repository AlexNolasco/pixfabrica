import { useEffect, useId, useMemo, useState } from 'react'
import { fetchWaveformPeaks } from '@/lib/waveformPeaks'

const FALLBACK_PEAKS = Array.from({ length: 96 }, () => 0.12)

/** Smooth mirrored waveform path (symmetric around vertical center). */
function mirroredWavePath(peaks: number[], width = 100, height = 100): string {
  const n = peaks.length
  if (n === 0) return ''

  const mid = height / 2
  const amp = mid * 0.92
  const step = n > 1 ? width / (n - 1) : 0

  const top = peaks.map((p, i) => ({
    x: i * step,
    y: mid - Math.min(1, Math.max(0, p)) * amp,
  }))
  const bot = peaks.map((p, i) => ({
    x: i * step,
    y: mid + Math.min(1, Math.max(0, p)) * amp,
  }))

  let d = `M 0 ${mid} L ${top[0].x} ${top[0].y}`

  for (let i = 1; i < n; i++) {
    const prev = top[i - 1]
    const curr = top[i]
    const cx = (prev.x + curr.x) / 2
    d += ` Q ${cx} ${prev.y} ${curr.x} ${curr.y}`
  }

  d += ` L ${bot[n - 1].x} ${bot[n - 1].y}`

  for (let i = n - 2; i >= 0; i--) {
    const curr = bot[i]
    const next = bot[i + 1]
    const cx = (curr.x + next.x) / 2
    d += ` Q ${cx} ${next.y} ${curr.x} ${curr.y}`
  }

  return `${d} Z`
}

export function AudioWaveformRender({ source }: { source: string }) {
  const gradientId = useId().replace(/:/g, '')
  const [peaks, setPeaks] = useState<number[]>(FALLBACK_PEAKS)

  useEffect(() => {
    let active = true
    void fetchWaveformPeaks(source).then((data) => {
      if (active) setPeaks(data)
    })
    return () => {
      active = false
    }
  }, [source])

  const path = useMemo(() => mirroredWavePath(peaks), [peaks])
  const hasSource = source.trim().length > 0

  return (
    <svg
      width="100%"
      height="100%"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="pointer-events-none"
      style={{ opacity: hasSource ? 1 : 0.35 }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgb(74 222 128 / 0.85)" />
          <stop offset="50%" stopColor="rgb(34 197 94 / 0.55)" />
          <stop offset="100%" stopColor="rgb(74 222 128 / 0.85)" />
        </linearGradient>
      </defs>
      <path d={path} fill={`url(#${gradientId})`} />
      <path
        d={path}
        fill="none"
        stroke="rgb(134 239 172 / 0.45)"
        strokeWidth="0.35"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
