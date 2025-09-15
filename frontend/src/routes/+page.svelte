<script>
  import Hero from '$lib/components/Hero.svelte';
  import FeaturedReaders from '$lib/components/FeaturedReaders.svelte';
  import HowItWorks from '$lib/components/HowItWorks.svelte';
  import Testimonials from '$lib/components/Testimonials.svelte';
  import CTA from '$lib/components/CTA.svelte';

  export let data;
</script>

<svelte:head>
  <title>SoulSeer - Connect with Gifted Psychic Readers</title>
  <meta name="description" content="Discover clarity and guidance. Connect with authentic psychic readers for live chat and video readings on SoulSeer." />
</svelte:head>

<div class="space-y-16 md:space-y-24">
  <Hero />
  <FeaturedReaders readers={data.featuredReaders} />
  <HowItWorks />
  <Testimonials />
  <CTA />
</div>
