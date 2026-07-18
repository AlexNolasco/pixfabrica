module.exports = {
  // Keep the Vite + API process alive after readiness is confirmed.
  daemon: true,
  run: [
    {
      method: "local.set",
      params: {
        // Do not reuse a URL from an earlier run while this launch is starting.
        url: null,
      },
    },
    {
      method: "shell.run",
      params: {
        path: "..",
        message: [
          "node pinokio/start.mjs",
        ],
        on: [{
          // start.mjs probes Vite before emitting this stable readiness line.
          event: "/(http:\\/\\/[0-9.:]+)/",
          done: true,
        }],
      },
    },
    {
      when: "{{input.event && input.event[1]}}",
      method: "local.set",
      params: {
        // Regex capture group is passed as input.event; use index 1.
        url: "{{input.event[1]}}",
      },
    },
  ],
}
