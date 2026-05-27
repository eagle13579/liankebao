import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', '');
  return {
    base: '/app/',
    plugins: [react(), tailwindcss()],
    define: {
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            'react-vendor': ['react', 'react-dom', 'react-router-dom'],
            'motion-vendor': ['motion', 'motion/react'],
            'ui-components': [
              './src/components/Carousel',
              './src/components/SpotlightCard',
              './src/components/BorderGlow',
              './src/components/Counter',
              './src/components/Dock',
              './src/components/DecryptedText',
              './src/components/SplashCursor',
            ],
            'auth-screens': ['./src/screens/AuthScreens'],
            'main-screens': ['./src/screens/MainScreens'],
            'product-screens': ['./src/screens/ProductScreens'],
            'order-screens': ['./src/screens/OrderScreens'],
            'admin-screens': ['./src/screens/AdminScreens'],
            'supply-demand-screens': ['./src/screens/SupplyDemandScreens', './src/screens/PostNeedScreen'],
            'recharge-screens': ['./src/screens/RechargeScreens'],
            'contacts-pages': ['./src/pages/ContactsPage', './src/pages/ContactsImportPage', './src/pages/ContactDetailPage', './src/pages/ContactMergePage'],
          },
        },
      },
    },
    server: {
      proxy: {
        '/lkapi': {
          target: 'http://localhost:8001',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/lkapi/, ''),
        },
      },
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify—file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
    },
  };
});
