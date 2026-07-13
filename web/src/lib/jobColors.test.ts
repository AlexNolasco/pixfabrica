/// <reference types="node" />

import assert from 'node:assert/strict'
import test from 'node:test'
import messages from '@/lib/i18n.messages.json'
import {
  displayExtractedFilename,
  extractedPaletteBasename,
  paletteSourceLabel,
  parsePaletteSource,
  type PaletteLabelTranslator,
} from '@/lib/jobColors'

const t: PaletteLabelTranslator = (key) => messages.en[key] ?? key

test('extractedPaletteBasename strips directory paths', () => {
  assert.equal(extractedPaletteBasename('media/ingest-abc.jpeg'), 'ingest-abc.jpeg')
  assert.equal(extractedPaletteBasename('C:\\Users\\me\\media\\cover.png'), 'cover.png')
})

test('displayExtractedFilename truncates long basenames', () => {
  const long = 'ingest-0bd457661fd7096e8d41.jpeg'
  assert.equal(displayExtractedFilename(long), 'ingest-0bd457661fd7096…')
})

test('paletteSourceLabel uses short basename for extracted palettes', () => {
  const label = paletteSourceLabel(
    {
      type: 'extracted',
      filename: 'media/ingest-0bd457661fd7096e8d41.jpeg',
    },
    t,
  )
  assert.equal(label, 'Extracted · ingest-0bd457661fd7096…')
})

test('paletteSourceLabel localizes named preset fallback', () => {
  const label = paletteSourceLabel(
    { type: 'named', theme: 'amber', variant: 'dark' },
    t,
  )
  assert.equal(label, 'Amber (Dark)')
})

test('parsePaletteSource normalizes extracted filenames', () => {
  const parsed = parsePaletteSource({
    type: 'extracted',
    filename: 'media/cover.jpg',
  })
  assert.deepEqual(parsed, { type: 'extracted', filename: 'cover.jpg' })
})
