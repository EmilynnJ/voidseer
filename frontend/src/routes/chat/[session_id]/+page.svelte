<script>
  import { onMount, onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import ChatBox from '$lib/components/ChatBox.svelte';
  import SessionTimer from '$lib/components/SessionTimer.svelte';

  let ws;
  let messages = [];
  let message = '';

  const session_id = $page.params.session_id;
  const token = localStorage.getItem('access_token');

  onMount(() => {
    ws = new WebSocket(`${import.meta.env.VITE_WS_URL}/readings/${session_id}?token=${token}`);

    ws.onmessage = (event) => {
      messages = [...messages, JSON.parse(event.data)];
    };

    ws.onclose = () => console.log('WebSocket closed');
  });

  onDestroy(() => {
    if (ws) ws.close();
  });

  function sendMessage() {
    if (ws && message) {
      ws.send(JSON.stringify({ type: 'chat', content: message }));
      message = '';
    }
  }
</script>

<div class="flex flex-col h-screen">
  <SessionTimer {session_id} />
  <ChatBox {messages} />
  <form on:submit|preventDefault={sendMessage} class="p-4">
    <input bind:value={message} class="w-full p-2 border" placeholder="Type a message..." />
    <Button type="submit">Send</Button>
  </form>
</div>
