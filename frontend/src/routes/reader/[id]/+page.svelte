<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { Button } from '$lib/components/ui/button';

  let reader = null;
  let availability = [];

  const id = $page.params.id;

  onMount(async () => {
    const token = localStorage.getItem('access_token');

    // Fetch reader details
    const res = await fetch(`/api/v1/readers/${id}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    reader = await res.json();

    // Fetch availability
    const availRes = await fetch(`/api/v1/readers/${id}/availability?start_time=${new Date().toISOString()}&end_time=${new Date(Date.now() + 7*24*60*60*1000).toISOString()}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    availability = await availRes.json();
  });

  async function bookSession(slot) {
    // Implement booking logic
    console.log('Booking', slot);
  }
</script>

<div class="p-8">
  <h1>{reader?.name}</h1>
  <p>Bio: {reader?.bio}</p>
  <h2>Availability</h2>
  <ul>
    {#each availability as slot}
      <li>{slot.start_time} - {slot.end_time} <Button on:click={() => bookSession(slot)}>Book</Button></li>
    {/each}
  </ul>
</div>
