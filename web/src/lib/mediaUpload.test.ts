/// <reference types="node" />

import assert from 'node:assert/strict'
import test from 'node:test'
import { mediaSourceApiPath } from '@/lib/mediaSourcePath'

test('mediaSourceApiPath maps flat upload basename', () => {
  assert.equal(
    mediaSourceApiPath('C:\\host\\pixfabrica\\media\\song.m4a'),
    '/media/song.m4a',
  )
})

test('mediaSourceApiPath maps nested gallery bundle path on Windows', () => {
  const source =
    'C:\\Users\\dev\\pixfabrica\\media\\bundles\\gallery\\starters\\tormentum\\3b71e1d5-a49c-d485-8e46-96ea723ce441.mp3'
  assert.equal(
    mediaSourceApiPath(source),
    '/media/bundles/gallery/starters/tormentum/3b71e1d5-a49c-d485-8e46-96ea723ce441.mp3',
  )
})

test('mediaSourceApiPath maps nested gallery bundle path on POSIX', () => {
  const source =
    '/home/dev/pixfabrica/media/bundles/gallery/starters/night-title/0d30a644-61a7-7fd2-67d0-739b51d0cf85.m4a'
  assert.equal(
    mediaSourceApiPath(source),
    '/media/bundles/gallery/starters/night-title/0d30a644-61a7-7fd2-67d0-739b51d0cf85.m4a',
  )
})

test('mediaSourceApiPath preserves remote URL pathname', () => {
  assert.equal(
    mediaSourceApiPath('https://cdn.example.com/media/clip.mp3?token=1'),
    '/media/clip.mp3',
  )
})
