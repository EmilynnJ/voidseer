<script lang="ts">
  import Header from '$lib/components/Header.svelte';
  import Footer from '$lib/components/Footer.svelte';
  import { Toaster } from 'svelte-sonner';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { handleTrack } from '$app/navigation';
  import '../app.css';
  
  // Handle theme changes
  onMount(() => {
    // Initialize theme from localStorage or use system preference
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
      document.documentElement.classList.add('dark');
    }
    
    // Track page view
    handleTrack($page.url);
    
    // Cleanup
    return () => {
      // Any cleanup code if needed
    };
  });
  
  // Handle theme toggle
  function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }
  
  // Export theme toggle function for child components
  export let themeToggle = toggleTheme;
</script>

<Toaster position="top-center" richColors closeButton />

<div class="flex flex-col min-h-screen bg-background text-foreground transition-colors duration-200">
  <Header bind:themeToggle />
  
  <main class="flex-grow">
    <div class="container mx-auto px-4 py-8">
      <slot />
    </div>
  </main>
  
  <Footer />
</div>

<!-- Global error boundary for the entire app -->
<svelte:head>
  <title>SoulSeer - Find Your Perfect Psychic Reader</title>
  <meta name="description" content="Connect with experienced psychic readers for live readings, tarot card readings, and spiritual guidance." />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="theme-color" content="#ffffff" />
  <link rel="icon" href="/favicon.ico" />
  <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
  
  <!-- Preconnect to external domains -->
  <link rel="preconnect" href="https://api.soulseer.com" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  
  <!-- Preload critical resources -->
  <link rel="preload" href="/fonts/Inter.var.woff2" as="font" type="font/woff2" crossorigin />
  
  <!-- Theme color for address bar -->
  <meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)" />
  <meta name="theme-color" content="#0f172a" media="(prefers-color-scheme: dark)" />
  
  <!-- iOS specific meta tags -->
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="default" />
  <meta name="apple-mobile-web-app-title" content="SoulSeer" />
  
  <!-- PWA manifest -->
  <link rel="manifest" href="/manifest.json" />
</svelte:head>
