import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:8000'

  return {
    base: './',
    server: { proxy: { '/api': { target: apiTarget, changeOrigin: true } } },
    preview: { proxy: { '/api': { target: apiTarget, changeOrigin: true } } },
  }
})
