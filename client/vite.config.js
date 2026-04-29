import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  preview: {
    port: parseInt(process.env.PORT) || 4173,
    host: true,
    allowedHosts: true,
  },
  server: {
    port: 5173,
    host: true,
  },
})
