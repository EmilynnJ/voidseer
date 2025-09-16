<script>
  import { goto } from '$app/navigation';
  import { Button } from '$lib/components/ui/button';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';

  let email = '';
  let password = '';
  let error = '';

  async function handleLogin() {
    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      if (!response.ok) {
        throw new Error('Login failed');
      }

      const { access_token } = await response.json();
      // Store token, e.g., in localStorage or cookie
      localStorage.setItem('access_token', access_token);
      goto('/dashboard');
    } catch (err) {
      error = err.message;
    }
  }
</script>

<div class="flex min-h-screen items-center justify-center">
  <div class="w-full max-w-md space-y-8 p-8">
    <h2 class="text-center text-3xl font-bold">Login to SoulSeer</h2>
    
    {#if error}
      <div class="text-red-500 text-center">{error}</div>
    {/if}
    
    <form on:submit|preventDefault={handleLogin} class="space-y-6">
      <div>
        <Label for="email">Email</Label>
        <Input id="email" type="email" bind:value={email} required />
      </div>
      
      <div>
        <Label for="password">Password</Label>
        <Input id="password" type="password" bind:value={password} required />
      </div>
      
      <Button type="submit" class="w-full">Login</Button>
    </form>
  </div>
</div>
