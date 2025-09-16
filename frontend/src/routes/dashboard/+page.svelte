<script>
  import { onMount } from 'svelte';
  import { Button } from '$lib/components/ui/button';
  import Header from '$lib/components/Header.svelte';
  import Sidebar from '$lib/components/Sidebar.svelte';

  let user = null;
  let sessions = [];

  onMount(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      goto('/login');
      return;
    }

    // Fetch user profile
    const userRes = await fetch('/api/v1/users/me', {
      headers: { Authorization: `Bearer ${token}` }
    });
    user = await userRes.json();

    // Fetch sessions
    const sessionsRes = await fetch('/api/v1/readings', {
      headers: { Authorization: `Bearer ${token}` }
    });
    sessions = await sessionsRes.json();
  });
</script>

<Header />
<div class="flex">
  <Sidebar />
  <main class="flex-1 p-8">
    <h1>Welcome, {user?.first_name}</h1>
    <h2>Your Sessions</h2>
    <ul>
      {#each sessions as session}
        <li>{session.id} - {session.status} with {session.reader.name}</li>
      {/each}
    </ul>
    <Button on:click={() => goto('/readers')}>Find Readers</Button>
  </main>
</div>
