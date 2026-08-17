import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Plain Vite config — no Figma Make plugins. Output is a static SPA in dist/.
export default defineConfig({
  base: '/',
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: true,
  },
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    include: ['d3-force', 'd3-zoom', 'd3-selection', 'louvain'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    dedupe: ['react', 'react-dom'],
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
  },
})
