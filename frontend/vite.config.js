import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built assets are served by the FastAPI app from frontend/dist (same origin as /events).
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true },
})
