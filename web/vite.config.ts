import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/nodass-ocean-dashboard/' : '/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/@tanstack/react-query/') ||
            id.includes('/zustand/')
          ) {
            return 'react'
          }
          if (id.includes('/chart.js/') || id.includes('/react-chartjs-2/')) {
            return 'charts'
          }
          if (id.includes('/maplibre-gl/')) {
            return 'maps'
          }
          if (id.includes('/deck.gl/') || id.includes('/@deck.gl/')) {
            return 'deck'
          }
          return 'vendor'
        },
      },
    },
  },
}))
