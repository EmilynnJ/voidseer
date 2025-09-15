<script>
  import { Search, UserPlus, MessageSquare, Wallet } from 'lucide-svelte';

  const steps = [
    {
      icon: Search,
      title: 'Discover Readers',
      description: 'Browse our community of authentic readers. Filter by specialties, tools, and availability to find the perfect match for you.'
    },
    {
      icon: UserPlus,
      title: 'Create Your Account',
      description: 'Sign up for a free account to connect with readers, add funds, and manage your sessions all in one place.'
    },
    {
      icon: Wallet,
      title: 'Add Funds Securely',
      description: 'Easily add funds to your account using our secure payment system. You only pay for the minutes you use.'
    },
    {
      icon: MessageSquare,
      title: 'Start Your Reading',
      description: 'Connect with your chosen reader via live chat or video call. Gain the clarity and guidance you seek.'
    }
  ];
</script>

<section class="py-16 md:py-24 bg-primary-foreground">
  <div class="container mx-auto px-4">
    <div class="text-center mb-12">
      <h2 class="text-3xl md:text-4xl font-bold text-primary">How It Works</h2>
      <p class="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">
        Connecting with a reader on SoulSeer is simple and secure. Here's how to get started in just a few steps.
      </p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
      {#each steps as step, i}
        <div class="text-center p-6 bg-card rounded-lg shadow-sm">
          <div class="flex items-center justify-center w-16 h-16 mx-auto mb-6 bg-primary text-primary-foreground rounded-full">
            <svelte:component this={step.icon} class="w-8 h-8" />
          </div>
          <h3 class="text-xl font-semibold text-card-foreground">{i + 1}. {step.title}</h3>
          <p class="mt-2 text-muted-foreground">{step.description}</p>
        </div>
      {/each}
    </div>
  </div>
</section>
