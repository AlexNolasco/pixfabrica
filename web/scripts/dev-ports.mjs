/** Shared dev port defaults — keep in sync with scripts/dev-ports.sh and README. */

export const DEFAULT_WEB_PORT = 5173
export const DEFAULT_API_PORT = 8000

export function resolveDevPorts(env = process.env) {
  const webPort = String(env.PIXFABRICA_WEB_PORT || DEFAULT_WEB_PORT)
  const apiPort = String(env.PIXFABRICA_API_PORT || DEFAULT_API_PORT)
  return { webPort, apiPort }
}

export function applyDevPortEnv(env = process.env) {
  const { webPort, apiPort } = resolveDevPorts(env)
  env.PIXFABRICA_WEB_PORT = webPort
  env.PIXFABRICA_API_PORT = apiPort
  return { webPort, apiPort }
}
