/// <reference types="node" />

import assert from 'node:assert/strict'
import test from 'node:test'
import {
  canMoveClipToTrack,
  clipDragId,
  clipTrackKind,
  parseClipDragId,
} from '@/lib/clipMove'
import type { Clip, Track } from '@/store/projectStore'

const skiaClip: Clip = {
  id: 'el-1',
  clip_type: 'std.image',
  label: 'Image',
  start: 0,
  duration: null,
  enabled: true,
  params: {},
}

const skiaTrack = (id: string, clips: Clip[] = [], enabled = true): Track => ({
  id,
  label: 'Skia',
  enabled,
  disableMode: 'bypass_compute',
  start: 0,
  duration: null,
  layout: 'fill',
  trackType: 'skia',
  clips,
})

const glTrack = (id: string, clips: Clip[] = []): Track => ({
  ...skiaTrack(id, clips),
  label: 'GL',
  trackType: 'gl',
})

const postTrack = (id: string, clips: Clip[] = []): Track => ({
  ...skiaTrack(id, clips),
  label: 'Post',
  trackType: 'post',
})

const catalogClips = [
  { clip_type: 'std.image', track_kind: 'skia' as const },
  { clip_type: 'std.particles', track_kind: 'gl' as const },
]

test('clipDragId round-trips through parseClipDragId', () => {
  const id = clipDragId('track-a', 'el-b')
  assert.deepEqual(parseClipDragId(id), { trackId: 'track-a', clipId: 'el-b' })
})

test('parseClipDragId rejects non-clip drag ids', () => {
  assert.equal(parseClipDragId('element:track-a:el-b'), null)
})

test('clipTrackKind returns catalog track_kind for known clip types', () => {
  assert.equal(clipTrackKind('std.image', catalogClips), 'skia')
  assert.equal(clipTrackKind('std.particles', catalogClips), 'gl')
})

test('clipTrackKind returns null for unknown clip types', () => {
  assert.equal(clipTrackKind('unknown.node', catalogClips), null)
})

test('canMoveClipToTrack allows skia clip onto empty skia track', () => {
  assert.equal(
    canMoveClipToTrack({
      fromTrackId: 'a',
      clip: skiaClip,
      destTrack: skiaTrack('b'),
      clipTrackKind: 'skia',
      config: { maxClipsPerTrack: 2 },
    }),
    true,
  )
})

test('canMoveClipToTrack rejects same track', () => {
  assert.equal(
    canMoveClipToTrack({
      fromTrackId: 'a',
      clip: skiaClip,
      destTrack: skiaTrack('a'),
      clipTrackKind: 'skia',
      config: { maxClipsPerTrack: 2 },
    }),
    false,
  )
})

test('canMoveClipToTrack rejects wrong track kind', () => {
  assert.equal(
    canMoveClipToTrack({
      fromTrackId: 'a',
      clip: skiaClip,
      destTrack: glTrack('b'),
      clipTrackKind: 'skia',
      config: { maxClipsPerTrack: 2 },
    }),
    false,
  )
})

test('canMoveClipToTrack rejects disabled destination track', () => {
  assert.equal(
    canMoveClipToTrack({
      fromTrackId: 'a',
      clip: skiaClip,
      destTrack: skiaTrack('b', [], false),
      clipTrackKind: 'skia',
      config: { maxClipsPerTrack: 2 },
    }),
    false,
  )
})

test('canMoveClipToTrack rejects full non-post track', () => {
  const full = skiaTrack('b', [
    { ...skiaClip, id: 'x' },
    { ...skiaClip, id: 'y' },
  ])
  assert.equal(
    canMoveClipToTrack({
      fromTrackId: 'a',
      clip: skiaClip,
      destTrack: full,
      clipTrackKind: 'skia',
      config: { maxClipsPerTrack: 2 },
    }),
    false,
  )
})

test('canMoveClipToTrack allows post track even when occupied', () => {
  const occupied = postTrack('b', [{ ...skiaClip, id: 'old' }])
  assert.equal(
    canMoveClipToTrack({
      fromTrackId: 'a',
      clip: { ...skiaClip, clip_type: 'std.bloom' },
      destTrack: occupied,
      clipTrackKind: 'post',
      config: { maxClipsPerTrack: 2 },
    }),
    true,
  )
})
