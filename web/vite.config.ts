import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const webPort = Number(env.PIXFABRICA_WEB_PORT ?? process.env.PIXFABRICA_WEB_PORT ?? 5173)
  const apiPort = Number(env.PIXFABRICA_API_PORT ?? process.env.PIXFABRICA_API_PORT ?? 8000)
  const apiOrigin = `http://localhost:${apiPort}`
  const apiWsOrigin = `ws://localhost:${apiPort}`

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: webPort,
      strictPort: true,
      proxy: {
        '/api': {
          target: apiOrigin,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/ws': {
          target: apiWsOrigin,
          ws: true,
          rewrite: (path) => path.replace(/^\/ws/, ''),
        },
      },
    },
  }
})
