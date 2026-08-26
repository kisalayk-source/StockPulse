import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    timeout: 600_000,
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    allowedHosts: ['stockapp', 'stockapp.local', 'stockapp.lan', '.lan', '.local'],
    proxy: apiProxy,
  },
  preview: {
    host: true,
    allowedHosts: ['stockapp', 'stockapp.local', 'stockapp.lan', '.lan', '.local'],
    proxy: apiProxy,
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
})
