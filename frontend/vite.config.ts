import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  plugins: [sveltekit()],
  resolve: {
    alias: {
      $lib: resolve('./src/lib'),
    }
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Proxy API requests to the backend server
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        // If you need to rewrite the path, uncomment and modify:
        // rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  // Optimize dependencies for faster builds
  optimizeDeps: {
    include: ['lucide-svelte'],
    exclude: ['@sveltejs/kit']
  },
  // Build configuration
  build: {
    target: 'esnext',
    sourcemap: true,
    minify: 'terser',
    cssMinify: true,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor modules into separate chunks
          'vendor': ['svelte', 'svelte/store'],
          // Split large dependencies into separate chunks
          'lucide': ['lucide-svelte']
        }
      }
    }
  },
  // CSS configuration
  css: {
    preprocessorOptions: {
      scss: {
        // Global SCSS variables/mixins available in all components
        additionalData: `@use "src/app.css" as *;`
      }
    }
  }
});
