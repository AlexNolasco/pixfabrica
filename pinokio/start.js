module.exports = {
  // Keep the Vite + API shells alive after URL capture.
  daemon: true,
  run: [
    {
      method: "shell.run",
      params: {
        env: {
          PIXFABRICA_WEB_PORT: "5173",
          PIXFABRICA_API_PORT: "8000",
        },
        path: "../web",
        message: [
          "pnpm dev:all",
        ],
        on: [{
          // Match the editor URL specifically so uvicorn :8000 is not captured first.
          // Vite prints http://localhost:5173/ (or 127.0.0.1).
          event: "/(http:\\/\\/(?:localhost|127\\.0\\.0\\.1):5173)/",
          done: true,
        }],
      },
    },
    {
      method: "local.set",
      params: {
        // Regex capture group is passed as input.event; use index 1.
        url: "{{input.event[1]}}",
      },
    },
  ],
}
