module.exports = {
  version: "7.0",
  title: "Pixfabrica",
  description:
    "Browser-based motion graphics editor for short-form video. Timeline clips, live preview, and MP4 export. https://github.com/AlexNolasco/pixfabrica",
  icon: "icon.png",
  pre: [
    {
      title: "Ollama",
      description: "Optional. Local LLM host for the compose agent.",
      href: "https://ollama.com/",
    },
  ],
  menu: async (kernel, info) => {
    let installed = info.exists(".venv") && info.exists("web/node_modules")
    let running = {
      install: info.running("pinokio/install.js"),
      start: info.running("pinokio/start.js"),
      update: info.running("pinokio/update.js"),
      reset: info.running("pinokio/reset.js"),
    }
    if (running.install) {
      return [
        {
          default: true,
          icon: "fa-solid fa-plug",
          text: "Installing",
          href: "pinokio/install.js",
        },
      ]
    } else if (installed) {
      if (running.start) {
        let local = info.local("pinokio/start.js")
        if (local && local.url) {
          return [
            {
              default: true,
              icon: "fa-solid fa-rocket",
              text: "Open Editor",
              href: local.url,
            },
            {
              icon: "fa-solid fa-terminal",
              text: "Terminal",
              href: "pinokio/start.js",
            },
            {
              icon: "fa-solid fa-book",
              text: "API Docs",
              href: "http://localhost:8000/docs",
            },
          ]
        } else {
          return [
            {
              default: true,
              icon: "fa-solid fa-terminal",
              text: "Terminal",
              href: "pinokio/start.js",
            },
          ]
        }
      } else if (running.update) {
        return [
          {
            default: true,
            icon: "fa-solid fa-terminal",
            text: "Updating",
            href: "pinokio/update.js",
          },
        ]
      } else if (running.reset) {
        return [
          {
            default: true,
            icon: "fa-solid fa-terminal",
            text: "Resetting",
            href: "pinokio/reset.js",
          },
        ]
      } else {
        return [
          {
            default: true,
            icon: "fa-solid fa-power-off",
            text: "Start",
            href: "pinokio/start.js",
          },
          {
            icon: "fa-solid fa-plug",
            text: "Update",
            href: "pinokio/update.js",
          },
          {
            icon: "fa-solid fa-plug",
            text: "Install",
            href: "pinokio/install.js",
          },
          {
            icon: "fa-regular fa-circle-xmark",
            text: "Reset",
            href: "pinokio/reset.js",
          },
        ]
      }
    } else {
      return [
        {
          default: true,
          icon: "fa-solid fa-plug",
          text: "Install",
          href: "pinokio/install.js",
        },
      ]
    }
  },
}
