import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

// node_modules lives in the same directory as this config file (deploy/docker/)
const nodeModulesPath = path.resolve(__dirname, 'node_modules');
const rootDir = path.resolve(__dirname, '../..');

export default defineConfig({
  root: rootDir,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(rootDir, 'src'),
    },
    // Tell Vite to look for node_modules in deploy/docker/ first
    moduleDirectory: [nodeModulesPath, 'node_modules'],
  },
  build: {
    outDir: path.resolve(__dirname, 'dist'),
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: undefined,
      },
    },
  },
  server: {
    port: 3099,
    proxy: {
      '/api': 'http://127.0.0.1:8001',
    },
    fs: {
      allow: [
        rootDir,
        nodeModulesPath,
      ],
    },
  },
  optimizeDeps: {
    // Ensure React and its JSX runtime are pre-bundled
    include: ['react', 'react-dom', 'react/jsx-dev-runtime', 'react/jsx-runtime'],
  },
});
