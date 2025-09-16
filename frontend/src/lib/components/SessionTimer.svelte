<script>
  export let session_id;
  import { onMount, onDestroy } from 'svelte';

  let time = 0;
  let interval;

  onMount(() => {
    // Fetch initial time or start timer
    interval = setInterval(() => {
      time += 1;
    }, 1000);
  });

  onDestroy(() => clearInterval(interval));
</script>

<div class="p-4 bg-blue-100">
  Session Time: {Math.floor(time / 60)}:{time % 60 < 10 ? '0' : ''}{time % 60}
</div>
