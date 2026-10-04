import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true }, // la API solo acepta este origen (CORS)
  test: {
    environment: 'jsdom',
    setupFiles: './src/pruebas/preparar.js',
    globals: true,
  },
})
