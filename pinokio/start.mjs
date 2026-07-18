import { spawn } from "node:child_process"

const WEB_URL = "http://127.0.0.1:5173"
const PROBE_URL = "http://127.0.0.1:5173"
const PROBE_INTERVAL_MS = 500
const STARTUP_TIMEOUT_MS = 180_000

const isWindows = process.platform === "win32"
const child = spawn("pnpm", ["dev:all"], {
  cwd: new URL("../web/", import.meta.url),
  env: {
    ...process.env,
    PIXFABRICA_WEB_HOST: "127.0.0.1",
    PIXFABRICA_WEB_PORT: "5173",
    PIXFABRICA_API_PORT: "8000",
  },
  shell: isWindows,
  stdio: ["inherit", "pipe", "pipe"],
})

child.stdout.pipe(process.stdout)
child.stderr.pipe(process.stderr)

const startedAt = Date.now()
let ready = false

async function waitUntilReady() {
  while (!ready && Date.now() - startedAt < STARTUP_TIMEOUT_MS) {
    try {
      const response = await fetch(PROBE_URL)
      if (response.ok) {
        ready = true
        console.log(`PIXFABRICA_READY ${WEB_URL}`)
        return
      }
    } catch {
      // Expected while Vite is starting.
    }
    await new Promise((resolve) => setTimeout(resolve, PROBE_INTERVAL_MS))
  }

  if (!ready) {
    console.error(`Pixfabrica did not become ready within ${STARTUP_TIMEOUT_MS / 1000} seconds.`)
    child.kill()
    process.exitCode = 1
  }
}

child.on("error", (error) => {
  console.error(`Failed to start Pixfabrica: ${error.message}`)
  process.exitCode = 1
})

child.on("exit", (code, signal) => {
  if (!ready && process.exitCode === undefined) {
    console.error(`Pixfabrica exited before becoming ready (${signal ?? code ?? "unknown"}).`)
  }
  process.exit(code ?? (signal ? 1 : 0))
})

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal))
}

console.log("Starting Pixfabrica. An Open Editor link will appear when it is ready...")
await waitUntilReady()
