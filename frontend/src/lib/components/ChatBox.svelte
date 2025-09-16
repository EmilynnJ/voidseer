<script>
  export let messages = [];
</script>

<div class="flex-1 overflow-y-auto p-4 space-y-4">
  {#each messages as msg}
    <div class="bg-gray-100 p-2 rounded">
      <p><strong>{msg.sender_id}:</strong> {msg.content}</p>
      <span class="text-xs text-gray-500">{msg.created_at}</span>
    </div>
  {/each}
</div>
