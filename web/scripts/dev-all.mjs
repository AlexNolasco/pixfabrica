/**
 * Start Vite + API with ports from PIXFABRICA_WEB_PORT / PIXFABRICA_API_PORT.
 * Run via: pnpm dev:all (from web/)
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { applyDevPortEnv } from './dev-ports.mjs'

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const rootDir = path.resolve(webDir, '..')
const isWin = process.platform === 'win32'

function loadDotEnv(filePath) {
  if (!fs.existsSync(filePath)) return
  for (const line of fs.readFileSync(filePath, 'utf8').split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq === -1) continue
    const key = trimmed.slice(0, eq).trim()
    const value = trimmed.slice(eq + 1).trim()
    if (process.env[key] === undefined) process.env[key] = value
  }
}

const SHUTDOWN_TIMEOUT_MS = 2000

function spawnDev(command, args, cwd) {
  const options = {
    cwd,
    stdio: 'inherit',
    env: process.env,
  }
  if (isWin) {
    // pnpm is a .cmd shim on Windows; a single shell string avoids EINVAL and DEP0190.
    // detached: CREATE_NEW_PROCESS_GROUP so CTRL+C hits only this script, not uvicorn/vite.
    return spawn([command, ...args].join(' '), {
      ...options,
      shell: true,
      detached: true,
    })
  }
  return spawn(command, args, options)
}

loadDotEnv(path.join(webDir, '.env'))
loadDotEnv(path.join(rootDir, 'api', '.env'))
const { webPort, apiPort } = applyDevPortEnv()

function killProcessTree(child) {
  if (!child?.pid || child.killed) return Promise.resolve()
  if (isWin) {
    // taskkill.exe is on PATH; avoid shell: true + args (Node DEP0190 on shutdown).
    // /F skips uvicorn --reload graceful shutdown, which hangs on Windows.
    return new Promise((resolve) => {
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
      })
      killer.on('close', resolve)
      killer.on('error', resolve)
    })
  }
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, SHUTDOWN_TIMEOUT_MS)
    child.once('exit', () => {
      clearTimeout(timer)
      resolve()
    })
    child.kill('SIGTERM')
  })
}

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((resolve) => setTimeout(resolve, ms)),
  ])
}

const children = [
  spawnDev('pnpm', ['exec', 'vite', '--port', webPort, '--strictPort'], webDir),
  spawnDev(
    'uv',
    [
      'run',
      '--package',
      'pixfabrica-api',
      'uvicorn',
      'pixfabrica_api.main:app',
      '--reload',
      '--port',
      apiPort,
    ],
    rootDir,
  ),
]

let exiting = false

async function shutdown(code = 0) {
  if (exiting) return
  exiting = true
  await withTimeout(
    Promise.all(children.map((child) => killProcessTree(child))),
    SHUTDOWN_TIMEOUT_MS,
  )
  process.exit(code)
}

for (const child of children) {
  child.on('exit', (code, signal) => {
    if (exiting) return
    shutdown(signal ? 1 : (code ?? 0))
  })
}

process.on('SIGINT', () => shutdown(130))
process.on('SIGTERM', () => shutdown(143))
