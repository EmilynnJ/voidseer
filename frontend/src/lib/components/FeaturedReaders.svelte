<script>
  import ReaderCard from '$lib/components/ReaderCard.svelte';
  import { Button } from '$lib/components/ui/button';

  export let readers = [];
</script>

<section class="py-16 md:py-24 bg-background">
  <div class="container mx-auto px-4">
    <div class="text-center mb-12">
      <h2 class="text-3xl md:text-4xl font-bold text-primary">Meet Our Gifted Readers</h2>
      <p class="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">
        Hand-picked for their authenticity, compassion, and unique abilities.
      </p>
    </div>
    
    {#if readers && readers.length > 0}
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
        {#each readers as reader}
          <ReaderCard {reader} />
        {/each}
      </div>
    {:else}
      <p class="text-center text-muted-foreground">No featured readers available at the moment.</p>
    {/if}

    <div class="text-center mt-12">
      <Button href="/readers" size="lg" variant="secondary">View All Readers</Button>
    </div>
  </div>
</section>
