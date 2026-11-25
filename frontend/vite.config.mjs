import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  // 127.0.0.1, not localhost: the backend listens on IPv4 only, and on Windows Node tries IPv6
  // (::1) for "localhost" first, which delays every proxied request.
  const apiTarget = env.VITE_API_TARGET || 'http://127.0.0.1:8000'

  return {
    base: './',
    server: { proxy: { '/api': { target: apiTarget, changeOrigin: true } } },
    preview: { proxy: { '/api': { target: apiTarget, changeOrigin: true } } },
  }
})
