/**
 * Client-side caps for memory and performance (not user settings).
 *
 * Other limit homes:
 * - `serverConfig.ts` — API/server-driven project and upload limits
 * - `previewConfig.ts` — live preview transport tuning
 * - `audioBufferCache.ts`, `waveformPeaks.ts` — module-local media caches
 */

/** Max undo steps in zundo `pastStates`; oldest entries are dropped. */
export const PROJECT_UNDO_HISTORY_LIMIT = 75
