import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Backend and frontend share one root .env (VITE_APP_NAME alongside
  // APP_NAME) rather than keeping a second frontend-only env file.
  envDir: '../',
})
