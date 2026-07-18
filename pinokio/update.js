module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        path: "..",
        message: "git pull",
      },
    },
    {
      method: "shell.run",
      params: {
        path: "..",
        message: [
          "uv sync --all-packages",
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        env: {
          CI: "true",
        },
        path: "../web",
        message: [
          "pnpm install",
        ],
      },
    },
  ],
}
