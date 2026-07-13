/// <reference types="node" />

import assert from 'node:assert/strict'
import test from 'node:test'
import { computeVideoBoomerangPlan, isBoomerangDerivativeSource } from '@/lib/videoBoomerang'

const meta = { duration: 30, fps: 24 }

test('computeVideoBoomerangPlan tiles cycles to fill job', () => {
  const plan = computeVideoBoomerangPlan(10, {}, 0, 0, meta)
  assert.deepEqual(plan, {
    legSourceSeconds: 10,
    outputDuration: 40,
    cycles: 2,
    capped: false,
  })
})

test('computeVideoBoomerangPlan tiles short clips past job end', () => {
  const plan = computeVideoBoomerangPlan(7, {}, 0, 0, meta)
  assert.ok(plan)
  assert.equal(plan.cycles, 3)
  assert.equal(plan.outputDuration, 42)
  assert.equal(plan.legSourceSeconds, 7)
})

test('computeVideoBoomerangPlan compresses one cycle when needed', () => {
  const plan = computeVideoBoomerangPlan(18.06, {}, 0, 0, meta)
  assert.ok(plan)
  assert.equal(plan.capped, true)
  assert.equal(plan.cycles, 1)
  assert.equal(plan.outputDuration, 30)
  assert.equal(plan.legSourceSeconds, 15)
})

test('isBoomerangDerivativeSource detects boomerang filenames', () => {
  assert.equal(isBoomerangDerivativeSource('/media/clip.boomerang-abc123.mp4'), true)
  assert.equal(isBoomerangDerivativeSource('clip.boomerang-abc.boomerang-def.mp4'), true)
  assert.equal(isBoomerangDerivativeSource('/media/clip.mp4'), false)
  assert.equal(isBoomerangDerivativeSource('boomerang-clip.mp4'), false)
})
