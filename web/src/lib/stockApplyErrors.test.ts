/// <reference types="node" />

import assert from 'node:assert/strict'
import test from 'node:test'
import { formatStockApplyError } from '@/lib/stockApplyErrors'
import { FALLBACK_UPLOAD_LIMITS } from '@/lib/serverConfig'

const serverConfig = {
  uploadLimits: { ...FALLBACK_UPLOAD_LIMITS },
}

test('formatStockApplyError maps byte limit to friendly video message', () => {
  const message = formatStockApplyError(
    {
      kind: 'video',
      code: 'apply_failed',
      message: 'remote file exceeds 15728640 byte limit for kind',
    },
    serverConfig,
  )
  assert.match(message, /15 MB/)
  assert.match(message, /too large/i)
})

test('formatStockApplyError maps byte limit from Pexels API JSON body', () => {
  const message = formatStockApplyError(
    {
      kind: 'photo',
      code: 'apply_failed',
      message:
        'Pexels request failed (422): {"detail":"remote file exceeds 10485760 byte limit for kind"}',
    },
    serverConfig,
  )
  assert.match(message, /10 MB/)
  assert.match(message, /too large/i)
})

test('formatStockApplyError uses timeline_full copy', () => {
  const message = formatStockApplyError({ kind: 'video', code: 'timeline_full' }, serverConfig)
  assert.match(message, /Timeline is full/i)
})
