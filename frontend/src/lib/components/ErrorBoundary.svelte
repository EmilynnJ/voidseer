<script lang="ts">
  import { onMount } from 'svelte';
  import { Button } from '$lib/components/ui/button';
  import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert';
  import { AlertCircle, RefreshCw } from 'lucide-svelte';

  export let error: Error | null = null;
  export let reset: () => void = () => window.location.reload();

  onMount(() => {
    // Clean up the error on component unmount
    return () => {
      error = null;
    };
  });
</script>

{#if error}
  <div class="container mx-auto p-6 max-w-4xl">
    <Alert variant="destructive">
      <AlertCircle class="h-4 w-4" />
      <AlertTitle>Something went wrong</AlertTitle>
      <AlertDescription>
        <p class="mb-4">{error.message || 'An unexpected error occurred.'}</p>
        {#if error.stack}
          <details class="mb-4">
            <summary class="text-sm cursor-pointer text-muted-foreground">Show error details</summary>
            <pre class="mt-2 p-2 bg-muted/50 rounded overflow-auto text-xs">{error.stack}</pre>
          </details>
        {/if}
        <div class="flex space-x-2">
          <Button variant="outline" on:click={reset}>
            <RefreshCw class="mr-2 h-4 w-4" />
            Try again
          </Button>
          <Button variant="outline" on:click={() => window.location.href = '/'}>
            Go to Home
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  </div>
{/if}

<slot />
