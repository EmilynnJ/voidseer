<script>
  import { Button } from '$lib/components/ui/button';
  import { Checkbox } from '$lib/components/ui/checkbox';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Slider } from '$lib/components/ui/slider';

  // Dummy data for filters
  const specialties = ['Tarot', 'Astrology', 'Mediumship', 'Numerology', 'Clairvoyance'];
  const tools = ['Crystals', 'Pendulum', 'Oracle Cards', 'Runes'];

  let priceRange = [0, 10];
</script>

<div class="bg-card p-6 rounded-lg shadow-sm sticky top-20">
  <h3 class="text-lg font-semibold mb-4">Filter Readers</h3>
  <form class="space-y-6">
    <div>
      <Label for="search">Keyword Search</Label>
      <Input id="search" placeholder="e.g., love, career" class="mt-2" />
    </div>

    <div>
      <Label>Specialties</Label>
      <div class="mt-2 space-y-2">
        {#each specialties as specialty}
          <div class="flex items-center space-x-2">
            <Checkbox id={specialty.toLowerCase()} />
            <Label for={specialty.toLowerCase()} class="font-normal">{specialty}</Label>
          </div>
        {/each}
      </div>
    </div>

    <div>
      <Label>Tools</Label>
      <div class="mt-2 space-y-2">
        {#each tools as tool}
          <div class="flex items-center space-x-2">
            <Checkbox id={tool.toLowerCase()} />
            <Label for={tool.toLowerCase()} class="font-normal">{tool}</Label>
          </div>
        {/each}
      </div>
    </div>

    <div>
      <Label for="price">Price Range ($/min)</Label>
      <div class="mt-2">
        <Slider bind:value={priceRange} max={25} step={0.5} />
        <div class="flex justify-between text-sm text-muted-foreground mt-2">
          <span>${priceRange[0].toFixed(2)}</span>
          <span>${priceRange[1].toFixed(2)}</span>
        </div>
      </div>
    </div>

    <div class="flex items-center space-x-2">
      <Checkbox id="available-now" />
      <Label for="available-now" class="font-normal">Available Now</Label>
    </div>

    <div class="flex flex-col space-y-2 pt-4">
        <Button type="submit">Apply Filters</Button>
        <Button type="reset" variant="ghost">Clear Filters</Button>
    </div>
  </form>
</div>
