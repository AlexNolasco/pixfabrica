/// <reference types="node" />

import assert from 'node:assert/strict'
import test from 'node:test'
import { computeVideoClipFit } from '@/lib/videoFit'

const meta = { duration: 30, fps: 24 }

test('computeVideoClipFit fits source length at normal playback rate', () => {
  const result = computeVideoClipFit(10, {}, 0, 0, meta)
  assert.deepEqual(result, { duration: 10, capped: false })
})

test('computeVideoClipFit accounts for playback rate and start offset', () => {
  const result = computeVideoClipFit(
    20,
    { start_offset: 5, playback_rate: 2 },
    0,
    0,
    meta,
  )
  assert.deepEqual(result, { duration: 7.5, capped: false })
})

test('computeVideoClipFit caps to remaining job time when source is longer', () => {
  const result = computeVideoClipFit(120, {}, 0, 0, meta)
  assert.deepEqual(result, { duration: 30, capped: true })
})

test('computeVideoClipFit caps using absolute clip start', () => {
  const result = computeVideoClipFit(40, {}, 0, 10, meta)
  assert.deepEqual(result, { duration: 20, capped: true })
})

test('computeVideoClipFit returns null for empty playable source', () => {
  assert.equal(computeVideoClipFit(5, { start_offset: 5 }, 0, 0, meta), null)
})
