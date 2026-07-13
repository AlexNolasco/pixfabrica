/// <reference types="node" />

import assert from 'node:assert/strict'
import test from 'node:test'
import { computeVideoReversePlan } from '@/lib/videoReverse'

const meta = { fps: 24 }

test('computeVideoReversePlan matches playable length', () => {
  const plan = computeVideoReversePlan(18, {}, meta)
  assert.deepEqual(plan, { sourceSeconds: 18, outputDuration: 18 })
})

test('computeVideoReversePlan respects start offset and rate', () => {
  const plan = computeVideoReversePlan(20, { start_offset: 5, playback_rate: 2 }, meta)
  assert.ok(plan)
  assert.equal(plan.sourceSeconds, 15)
  assert.equal(plan.outputDuration, 7.5)
})
