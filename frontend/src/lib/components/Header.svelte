<script>
  import { page } from '$app/stores';
  import { Button } from '$lib/components/ui/button';
  import { Sheet, SheetContent, SheetTrigger } from '$lib/components/ui/sheet';
  import { Menu, X } from 'lucide-svelte';

  let open = false;

  const mainNav = [
    { href: '/readers', label: 'Find a Reader' },
    { href: '/how-it-works', label: 'How It Works' },
    { href: '/about', label: 'About Us' },
    { href: '/blog', label: 'Blog' }
  ];

  // TODO: Replace with actual user store
  const user = null; // or { name: 'Emily' }
</script>

<header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
  <div class="container flex h-14 items-center">
    <div class="mr-4 hidden md:flex">
      <a href="/" class="mr-6 flex items-center space-x-2">
        <!-- Add your logo here -->
        <span class="font-bold">SoulSeer</span>
      </a>
      <nav class="flex items-center space-x-6 text-sm font-medium">
        {#each mainNav as item}
          <a href={item.href} class:text-foreground={$page.url.pathname === item.href} class:text-muted-foreground={$page.url.pathname !== item.href} class="transition-colors hover:text-foreground/80">
            {item.label}
          </a>
        {/each}
      </nav>
    </div>

    <div class="md:hidden">
      <Sheet bind:open>
        <SheetTrigger asChild let:builder>
          <Button builders={[builder]} variant="ghost" size="icon">
            <Menu class="h-5 w-5" />
            <span class="sr-only">Toggle Menu</span>
          </Button>
        </SheetTrigger>
        <SheetContent side="left">
          <div class="flex flex-col space-y-4">
            <a href="/" class="mr-6 flex items-center space-x-2">
              <span class="font-bold">SoulSeer</span>
            </a>
            {#each mainNav as item}
              <a href={item.href} on:click={() => open = false} class:text-foreground={$page.url.pathname === item.href} class:text-muted-foreground={$page.url.pathname !== item.href} class="transition-colors hover:text-foreground/80">
                {item.label}
              </a>
            {/each}
          </div>
        </SheetContent>
      </Sheet>
    </div>

    <div class="flex flex-1 items-center justify-between space-x-2 md:justify-end">
      {#if user}
        <Button href="/dashboard">Dashboard</Button>
      {:else}
        <nav class="flex items-center space-x-2">
          <Button href="/login" variant="ghost">Log In</Button>
          <Button href="/register">Sign Up</Button>
        </nav>
      {/if}
    </div>
  </div>
</header>
