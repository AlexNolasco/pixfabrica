/// <reference types="node" />

import assert from 'node:assert/strict'
import test from 'node:test'
import { DEFAULT_JOB_COLORS } from '@/lib/jobColors'
import {
  backgroundLuminance,
  deriveAccentFromPrimary,
  generateJobPalette,
  inferThemeVariant,
  isValidJobPalette,
  resolveGenerationVariant,
} from '@/lib/generateJobPalette'

test('inferThemeVariant uses background luminance threshold', () => {
  assert.equal(inferThemeVariant('#231b10'), 'dark')
  assert.equal(inferThemeVariant('#fafafa'), 'light')
})

test('resolveGenerationVariant prefers named preset variant', () => {
  assert.equal(
    resolveGenerationVariant(
      { type: 'named', theme: 'amber', variant: 'light' },
      DEFAULT_JOB_COLORS,
    ),
    'light',
  )
})

test('resolveGenerationVariant infers from custom palette background', () => {
  assert.equal(
    resolveGenerationVariant({ type: 'custom' }, DEFAULT_JOB_COLORS),
    'dark',
  )
})

test('generateJobPalette returns valid analogous palettes', () => {
  const dark = generateJobPalette('dark')
  const light = generateJobPalette('light')
  assert.equal(isValidJobPalette(dark), true)
  assert.equal(isValidJobPalette(light), true)
  assert.ok(backgroundLuminance(dark.background) < backgroundLuminance(dark.primary))
  assert.ok(backgroundLuminance(light.background) > backgroundLuminance(light.primary))
})

test('deriveAccentFromPrimary shifts saturated hues', () => {
  const accent = deriveAccentFromPrimary('#f1c371')
  assert.notEqual(accent, '#f1c371')
  assert.match(accent, /^#[0-9a-f]{6}$/)
})
