<script>
  import { Badge } from '$lib/components/ui/badge';
  import { Button } from '$lib/components/ui/button';
  import { Star } from 'lucide-svelte';

  export let reader;

  function formatRate(rate) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(rate);
  }
</script>

<a href={`/readers/${reader.username}`} class="block border rounded-lg overflow-hidden shadow-sm hover:shadow-lg transition-shadow duration-300 bg-card">
  <div class="relative">
    <img src={reader.profile_image_url || '/placeholder-avatar.jpg'} alt={reader.display_name} class="w-full h-48 object-cover" />
    {#if reader.is_online}
      <span class="absolute top-2 right-2 flex h-3 w-3">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
      </span>
    {/if}
  </div>
  <div class="p-4">
    <div class="flex items-center justify-between">
      <h3 class="text-lg font-semibold text-card-foreground truncate">{reader.display_name}</h3>
      <div class="flex items-center gap-1 text-sm text-muted-foreground">
        <Star class="w-4 h-4 text-yellow-400" />
        <span>{reader.average_rating.toFixed(1)}</span>
      </div>
    </div>
    <p class="text-sm text-muted-foreground mt-1 truncate">{reader.tagline}</p>
    
    <div class="mt-3 flex flex-wrap gap-2">
      {#each reader.specialties.slice(0, 3) as specialty}
        <Badge variant="secondary">{specialty}</Badge>
      {/each}
    </div>

    <div class="mt-4 flex items-center justify-between">
        <p class="text-lg font-bold text-primary">{formatRate(reader.rate_per_minute)}/min</p>
        <Button size="sm" disabled={!reader.is_available}>Chat Now</Button>
    </div>
  </div>
</a>
