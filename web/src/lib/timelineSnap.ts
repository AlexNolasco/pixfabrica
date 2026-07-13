/** Quantize time for timeline trim (seconds stored as floats). */
export function snapTimelineTrim(t: number, fps: number, snapWholeSeconds: boolean): number {
  if (snapWholeSeconds) return Math.round(t)
  const q = 1 / fps
  return Math.round(t / q) * q
}

/** Keep a non-degenerate span inside [0, jobDuration]. */
export function clampSpanToJob(start: number, end: number, jobDuration: number, minLen: number): [number, number] {
  let s = Math.max(0, start)
  let e = Math.min(jobDuration, end)
  if (e - s < minLen) {
    e = Math.min(jobDuration, s + minLen)
  }
  if (e > jobDuration) {
    s = Math.max(0, jobDuration - minLen)
    e = jobDuration
  }
  return [s, e]
}
