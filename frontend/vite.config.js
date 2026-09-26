import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Fixed port so it matches the backend's CORS allow-list (FRONTEND_ORIGINS).
  server: { port: 5180, strictPort: true },
  preview: { port: 5180, strictPort: true },
})
