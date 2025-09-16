<script>
  import { page } from '$app/stores';
  import { Button } from '$lib/components/ui/button';

  const navItems = [
    { label: 'Dashboard', href: '/dashboard' },
    { label: 'Readers', href: '/readers' },
    { label: 'Sessions', href: '/sessions' },
    { label: 'Profile', href: '/profile' },
    { label: 'Logout', href: '/logout' }
  ];
</script>

<nav class="w-64 h-screen bg-gray-100 p-4">
  <ul class="space-y-2">
    {#each navItems as item}
      <li>
        <Button variant="ghost" class="w-full justify-start" href={item.href}>
          {item.label}
        </Button>
      </li>
    {/each}
  </ul>
</nav>
