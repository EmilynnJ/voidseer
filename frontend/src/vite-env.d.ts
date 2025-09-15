/// <reference types="@sveltejs/kit" />
/// <reference types="vite/client" />

// Add types for Vite environment variables
interface ImportMetaEnv {
  readonly VITE_APP_NAME: string;
  readonly VITE_APP_VERSION: string;
  readonly VITE_API_BASE_URL: string;
  readonly VITE_SENTRY_DSN?: string;
  // Add other environment variables here
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Add types for $app/stores
declare namespace App {
  interface Locals {
    user?: {
      id: string;
      name: string;
      email: string;
      // Add other user properties as needed
    };
    // Add other custom properties to locals if needed
  }

  interface PageData {
    // Add page data types here
  }

  interface Platform {
    // Add platform specific types here
  }
}

// Add types for $lib
/// <reference types="@sveltejs/kit" />
declare module '$lib' {
  // Add any lib-specific types here
}

// Add types for other modules as needed
declare module '*.svelte' {
  import type { ComponentType } from 'svelte';
  const component: ComponentType;
  export default component;
}

declare module '*.svg' {
  import type { ComponentType, SvelteComponentTyped } from 'svelte';
  import type { SVGAttributes } from 'svelte/elements';

  const content: ComponentType<SvelteComponentTyped<SVGAttributes<SVGSVGElement>>>;
  export default content;
}

declare module '*.svg?component' {
  import type { ComponentType, SvelteComponentTyped } from 'svelte';
  import type { SVGAttributes } from 'svelte/elements';

  const content: ComponentType<SvelteComponentTyped<SVGAttributes<SVGSVGElement>>>;
  export default content;
}

declare module '*.svg?src' {
  const content: string;
  export default content;
}

declare module '*.svg?url' {
  const content: string;
  export default content;
}

// Add types for global browser objects
declare const __APP_VERSION__: string;
