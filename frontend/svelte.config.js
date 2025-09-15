import adapter from '@sveltejs/adapter-auto';
import { vitePreprocess } from '@sveltejs/kit/vite';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  // Enable Svelte preprocessing with PostCSS
  preprocess: [
    vitePreprocess({
      postcss: true,
    }),
  ],

  kit: {
    // Use the auto adapter (supports Vercel, Netlify, etc.)
    adapter: adapter({
      // Enable pre-rendering for better performance
      precompress: true,
      
      // Enable edge functions if your hosting supports it
      edge: false,
      
      // External dependencies that shouldn't be bundled
      external: [],
      
      // Output directory for the build
      out: 'build',
    }),
    
    // Set up path aliases for cleaner imports
    alias: {
      $lib: './src/lib',
      $components: './src/lib/components',
      $assets: './src/lib/assets',
      $stores: './src/lib/stores',
      $utils: './src/lib/utils',
      $types: './src/lib/types',
      $api: './src/lib/api',
      $constants: './src/constants',
    },
    
    // CSRF protection
    csrf: {
      checkOrigin: process.env.NODE_ENV === 'production',
    },
    
    // Service worker configuration for PWA
    serviceWorker: {
      register: true,
      files: (filepath) => !/.*\.(test|spec)\.[jt]s$/.test(filepath),
    },
    
    // Version configuration for cache busting
    version: {
      name: process.env.npm_package_version || '0.0.1',
    },
    
    // Environment variables that should be accessible on the client
    env: {
      publicPrefix: 'PUBLIC_',
    },
    
    // Output directory for the build
    outDir: '.svelte-kit',
    
    // Files configuration
    files: {
      assets: 'static',
      hooks: 'src/hooks',
      lib: 'src/lib',
      params: 'src/params',
      routes: 'src/routes',
      serviceWorker: 'src/service-worker',
      appTemplate: 'src/app.html',
      errorTemplate: 'src/error.html',
    },
    
    // TypeScript configuration
    typescript: {
      config: (config) => config,
    },
    
    // Package configuration
    package: {
      dir: 'package',
      emitTypes: true,
      exports: (filepath) => {
        // Only include .svelte files in the package
        return filepath.endsWith('.svelte');
      },
      files: () => true,
    },
  },
  
  // Vite configuration
  vite: {
    // This will be merged with the Vite config in vite.config.ts
    // Add any Svelte-specific Vite config here
  },
};

export default config;
