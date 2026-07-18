module.exports = {
  run: [
    // Toolchain: prefer Pinokio-provided binaries; bootstrap only when missing.
    {
      when: "{{!which('uv')}}",
      method: "shell.run",
      params: {
        shell: "{{which('bash')}}",
        message: "curl -LsSf https://astral.sh/uv/install.sh | sh",
      },
    },
    {
      when: "{{!which('node')}}",
      method: "shell.run",
      params: {
        message: "conda install -y -c conda-forge nodejs",
      },
    },
    {
      when: "{{!which('pnpm')}}",
      method: "shell.run",
      params: {
        message: "npm install -g pnpm",
      },
    },
    {
      when: "{{!which('ffmpeg')}}",
      method: "shell.run",
      params: {
        message: "conda install -y -c conda-forge ffmpeg",
      },
    },
    // Python workspace (.venv at monorepo root)
    {
      method: "shell.run",
      params: {
        path: "..",
        message: [
          "uv sync --all-packages",
        ],
      },
    },
    // Web dependencies
    {
      method: "shell.run",
      params: {
        env: {
          // Non-interactive install under Pinokio (no TTY prompts).
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
