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
        path: "../web",
        message: [
          "pnpm install",
        ],
      },
    },
  ],
}
