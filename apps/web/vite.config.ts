import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
      // Grafana serves from the /grafana sub-path itself (GF_SERVER_SERVE_FROM_SUB_PATH), so no rewrite.
      '/grafana': { target: 'http://localhost:3000', ws: true, changeOrigin: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Rollup otherwise co-locates Vite's lazy-import helper with the first lazy chunk that
          // needs it (three), which makes the entry preload the whole 3D stack.
          if (id.includes('vite/preload-helper')) return 'vendor';
          if (!id.includes('node_modules')) return undefined;
          if (/[\\/]node_modules[\\/](antd|@ant-design|rc-[^\\/]+|@rc-component)[\\/]/.test(id)) return 'antd';
          // three.js and R3F are only imported from the lazy 3D views; a chunk of their own keeps them
          // out of the shared vendor chunk that every other page loads.
          if (/[\\/]node_modules[\\/](three|three-[^\\/]+|@react-three|troika-[^\\/]+|camera-controls|maath|meshline|stats-gl|detect-gpu|hls\.js|@mediapipe|react-reconciler|its-fine|suspend-react|@use-gesture|tunnel-rat|@monogrid)[\\/]/.test(id))
            return 'three';
          return 'vendor';
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    restoreMocks: true,
    testTimeout: 20_000,
  },
});
