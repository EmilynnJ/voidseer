<script>
  const links = {
    company: [
      { href: '/about', label: 'About Us' },
      { href: '/careers', label: 'Careers' },
      { href: '/press', label: 'Press' },
      { href: '/blog', label: 'Blog' }
    ],
    support: [
      { href: '/contact', label: 'Contact Us' },
      { href: '/faq', label: 'FAQ' },
      { href: '/terms', label: 'Terms of Service' },
      { href: '/privacy', label: 'Privacy Policy' }
    ],
    connect: [
      { href: '#', label: 'Facebook' },
      { href: '#', label: 'Instagram' },
      { href: '#', label: 'Twitter' },
      { href: '#', label: 'TikTok' }
    ]
  };
</script>

<footer class="bg-muted text-muted-foreground">
  <div class="container mx-auto px-4 py-12">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-8">
      <div>
        <h3 class="font-semibold text-foreground">Company</h3>
        <ul class="mt-4 space-y-2">
          {#each links.company as item}
            <li><a href={item.href} class="hover:text-foreground transition-colors">{item.label}</a></li>
          {/each}
        </ul>
      </div>
      <div>
        <h3 class="font-semibold text-foreground">Support</h3>
        <ul class="mt-4 space-y-2">
          {#each links.support as item}
            <li><a href={item.href} class="hover:text-foreground transition-colors">{item.label}</a></li>
          {/each}
        </ul>
      </div>
      <div>
        <h3 class="font-semibold text-foreground">Connect</h3>
        <ul class="mt-4 space-y-2">
          {#each links.connect as item}
            <li><a href={item.href} class="hover:text-foreground transition-colors">{item.label}</a></li>
          {/each}
        </ul>
      </div>
      <div>
        <h3 class="font-semibold text-foreground">SoulSeer</h3>
        <p class="mt-4">Find your clarity.</p>
      </div>
    </div>
    <div class="mt-12 border-t pt-8 text-center text-sm">
      <p>&copy; {new Date().getFullYear()} SoulSeer. All rights reserved.</p>
    </div>
  </div>
</footer>
