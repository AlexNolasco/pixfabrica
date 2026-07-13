/// <reference types="node" />

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import { DEFAULT_JOB_COLORS, DEFAULT_PALETTE_SOURCE } from '@/lib/jobColors'
import { cloneFontPalette, DEFAULT_FONT_PALETTE } from '@/lib/typography'
import {
  fromRenderJob,
  fromWebProjectJson,
  toRenderJob,
  type RenderJobJson,
} from '@/lib/renderJob'

const HELLO_JSON = join(
  import.meta.dirname,
  '../../../api/media/gallery/welcome/Hello.json',
)

test('toRenderJob preserves track storage order for mid-stack post tracks', () => {
  const job = toRenderJob({
    meta: {
      title: 't',
      author: '',
      fps: 24,
      duration: 15,
      width: 1080,
      height: 1080,
      exportQuality: 'master',
    },
    tracks: [
      {
        id: 'track-skia-back',
        label: 'Skia back',
        enabled: true,
        disableMode: 'bypass_compute',
        start: 0,
        duration: null,
        layout: 'fill',
        trackType: 'skia',
        clips: [],
      },
      {
        id: 'track-gl',
        label: 'GL',
        enabled: true,
        disableMode: 'bypass_compute',
        start: 0,
        duration: null,
        layout: 'fill',
        trackType: 'gl',
        clips: [],
      },
      {
        id: 'track-post',
        label: 'Post',
        enabled: true,
        disableMode: 'bypass_compute',
        start: 12,
        duration: 3,
        layout: 'fill',
        trackType: 'post',
        clips: [
          {
            id: 'el-post',
            clip_type: 'std-pixelate',
            label: 'Pixelate',
            start: 0,
            duration: null,
            enabled: true,
            params: { size: 0.015, opacity: 1 },
          },
        ],
      },
      {
        id: 'track-skia-front',
        label: 'Skia front',
        enabled: true,
        disableMode: 'bypass_compute',
        start: 0,
        duration: null,
        layout: 'fill',
        trackType: 'skia',
        clips: [],
      },
    ],
    sounds: [],
    projectSettings: [],
    typography: DEFAULT_FONT_PALETTE,
    colors: DEFAULT_JOB_COLORS,
    paletteSource: DEFAULT_PALETTE_SOURCE,
  })

  assert.deepEqual(job.tracks?.map((track) => track.id), [
    'track-skia-back',
    'track-gl',
    'track-post',
    'track-skia-front',
  ])
})

test('toRenderJob omits layout for post tracks', () => {
  const job = toRenderJob({
    meta: {
      title: 't',
      author: '',
      fps: 24,
      duration: 8,
      width: 1280,
      height: 720,
      exportQuality: 'master',
    },
    tracks: [
      {
        id: 'track-skia',
        label: 'Skia',
        enabled: true,
        disableMode: 'bypass_compute',
        start: 0,
        duration: null,
        layout: 'horizontal',
        trackType: 'skia',
        clips: [],
      },
      {
        id: 'track-post',
        label: 'Post',
        enabled: true,
        disableMode: 'bypass_compute',
        start: 0,
        duration: null,
        layout: 'vertical',
        trackType: 'post',
        clips: [],
      },
    ],
    sounds: [],
    projectSettings: [],
    typography: DEFAULT_FONT_PALETTE,
    colors: DEFAULT_JOB_COLORS,
    paletteSource: DEFAULT_PALETTE_SOURCE,
  })

  const skia = job.tracks?.find((track) => track.id === 'track-skia')
  const post = job.tracks?.find((track) => track.id === 'track-post')
  assert.deepEqual(skia?.layout, { type: 'horizontal' })
  assert.equal(post?.layout, undefined)
})

test('header_fraction roundtrips on split layouts', () => {
  const exported = toRenderJob({
    meta: {
      title: 't',
      author: '',
      fps: 24,
      duration: 8,
      width: 1280,
      height: 720,
      exportQuality: 'master',
    },
    tracks: [
      {
        id: 'track-v',
        label: 'Vertical',
        enabled: true,
        disableMode: 'bypass_compute',
        start: 0,
        duration: null,
        layout: 'vertical',
        headerFraction: 0.2,
        trackType: 'gl',
        clips: [
          {
            id: 'el-a',
            clip_type: 'std-star-nest-gl',
            label: 'Effect',
            start: 0,
            duration: null,
            enabled: true,
            params: {},
          },
          {
            id: 'el-b',
            clip_type: 'std-teleprompter-caption',
            label: 'Lyrics',
            start: 0,
            duration: null,
            enabled: true,
            params: {},
          },
        ],
      },
      {
        id: 'track-h',
        label: 'Horizontal',
        enabled: true,
        disableMode: 'bypass_compute',
        start: 0,
        duration: null,
        layout: 'horizontal',
        headerFraction: null,
        trackType: 'skia',
        clips: [],
      },
    ],
    sounds: [],
    projectSettings: [],
    typography: DEFAULT_FONT_PALETTE,
    colors: DEFAULT_JOB_COLORS,
    paletteSource: DEFAULT_PALETTE_SOURCE,
  })

  const vertical = exported.tracks?.find((track) => track.id === 'track-v')
  const horizontal = exported.tracks?.find((track) => track.id === 'track-h')
  assert.deepEqual(vertical?.layout, { type: 'vertical', header_fraction: 0.2 })
  assert.deepEqual(horizontal?.layout, { type: 'horizontal' })

  const imported = fromRenderJob(exported)
  assert.equal(imported.tracks[0]?.headerFraction, 0.2)
  assert.equal(imported.tracks[1]?.headerFraction, null)
})

test('typography import/export roundtrip preserves reference sizes at non-1080 height', () => {
  const typography = cloneFontPalette(DEFAULT_FONT_PALETTE)
  const exported = toRenderJob({
    meta: {
      title: 't',
      author: '',
      fps: 30,
      duration: 10,
      width: 1080,
      height: 1920,
      exportQuality: 'master',
    },
    tracks: [],
    sounds: [],
    projectSettings: [],
    typography,
    colors: DEFAULT_JOB_COLORS,
    paletteSource: DEFAULT_PALETTE_SOURCE,
  })

  const imported = fromRenderJob(exported)
  assert.equal(imported.typography.body_medium.size, typography.body_medium.size)
  assert.equal(imported.typography.title_large.size, typography.title_large.size)

  const reexported = toRenderJob({
    meta: imported.meta,
    tracks: imported.tracks,
    sounds: imported.sounds,
    projectSettings: [],
    typography: imported.typography,
    colors: imported.colors,
    paletteSource: imported.paletteSource,
  })
  const reimported = fromRenderJob(reexported)
  assert.equal(reimported.typography.body_medium.size, typography.body_medium.size)
})

test('Hello.json import/export preserves post track timing and pixelate params', () => {
  const raw = JSON.parse(readFileSync(HELLO_JSON, 'utf8')) as RenderJobJson
  const imported = fromWebProjectJson(raw)
  const post = imported.tracks.find((track) => track.trackType === 'post')
  assert.ok(post)
  assert.equal(post.start, 7)
  assert.equal(post.duration, 3)
  assert.equal(post.clips[0]?.clip_type, 'std-pixelate')
  assert.equal(post.clips[0]?.params.size, 0.015)

  const exported = toRenderJob({
    meta: imported.meta,
    tracks: imported.tracks,
    sounds: imported.sounds,
    projectSettings: [],
    typography: imported.typography,
    colors: imported.colors,
    paletteSource: imported.paletteSource,
  })

  const postJson = exported.tracks?.find((track) => track.clip_type === 'std-post-track')
  assert.ok(postJson)
  assert.equal(postJson.start, 7)
  assert.equal(postJson.duration, 3)
  assert.equal(postJson.clips?.[0]?.clip_type, 'std-pixelate')
  assert.equal(postJson.clips?.[0]?.size, 0.015)
  assert.equal(exported.tracks?.at(-1)?.clip_type, 'std-post-track')
})

test('legacy post track layout/clips normalize on roundtrip', () => {
  const raw: RenderJobJson = {
    title: 't',
    description: '',
    width: 1280,
    height: 720,
    fps: 24,
    duration: 8,
    tracks: [
      {
        clip_type: 'std-post-track',
        id: 'track-post',
        start: 0,
        duration: null,
        enabled: true,
        disable_mode: 'bypass_compute',
        layout: { type: 'horizontal' },
        transition_in: null,
        transition_out: null,
        clips: [
          { clip_type: 'std-scanlines', id: 'post-1', enabled: true },
          { clip_type: 'std-pixelate', id: 'post-2', enabled: true },
        ],
      },
    ],
    sounds: [],
  }

  const imported = fromRenderJob(raw)
  assert.equal(imported.tracks[0]?.trackType, 'post')
  assert.equal(imported.tracks[0]?.layout, 'fill')
  assert.equal(imported.tracks[0]?.clips.length, 1)
  assert.equal(imported.tracks[0]?.clips[0]?.id, 'post-1')

  const exported = toRenderJob({
    meta: imported.meta,
    tracks: imported.tracks,
    sounds: imported.sounds,
    projectSettings: [],
    typography: imported.typography,
    colors: imported.colors,
    paletteSource: imported.paletteSource,
  })

  const post = exported.tracks?.find((track) => track.id === 'track-post')
  assert.equal(post?.layout, undefined)
  assert.equal(post?.clips?.length, 1)
  assert.equal(post?.clips?.[0]?.id, 'post-1')
})

test('author roundtrips through render job JSON', () => {
  const exported = toRenderJob({
    meta: {
      title: 'Song',
      author: 'Jane Doe',
      fps: 30,
      duration: 10,
      width: 1080,
      height: 1920,
      exportQuality: 'master',
    },
    tracks: [],
    sounds: [],
    projectSettings: [],
    typography: DEFAULT_FONT_PALETTE,
    colors: DEFAULT_JOB_COLORS,
    paletteSource: DEFAULT_PALETTE_SOURCE,
  })
  assert.equal(exported.author, 'Jane Doe')
  const imported = fromRenderJob(exported)
  assert.equal(imported.meta.author, 'Jane Doe')
})
