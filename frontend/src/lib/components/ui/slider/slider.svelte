<script lang="ts">
  import * as SliderPrimitive from 'bits-ui';
  import { cn } from '$lib/utils';

  type $$Props = {
    class?: string;
    disabled?: boolean;
  } & SliderPrimitive.SliderProps;

  export let value: number[] = [0];
  export let min = 0;
  export let max = 100;
  export let step = 1;
  export let disabled = false;
  
  let className: string | undefined = undefined;
  export { className as class };

  // Handle change event
  function handleChange(e: CustomEvent<number[]>) {
    value = e.detail;
    const event = new CustomEvent('change', { detail: e.detail });
    dispatchEvent(event);
  }
</script>

<SliderPrimitive.Root
  bind:value
  {min}
  {max}
  {step}
  {disabled}
  on:change={handleChange}
  class={cn(
    "relative flex w-full touch-none select-none items-center",
    className
  )}
  {...$$restProps}
>
  <SliderPrimitive.Track 
    class="relative h-2 w-full grow overflow-hidden rounded-full bg-secondary"
  >
    <SliderPrimitive.Range class="absolute h-full bg-primary" />
  </SliderPrimitive.Track>
  
  {#each value as _, i (i)}
    <SliderPrimitive.Thumb
      data-index={i}
      class="block h-5 w-5 rounded-full border-2 border-primary bg-background ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
    />
  {/each}
</SliderPrimitive.Root>
