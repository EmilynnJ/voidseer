<script>
  import { onMount, onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import SessionTimer from '$lib/components/SessionTimer.svelte';

  let localVideo;
  let remoteVideo;
  let peerConnection;

  const session_id = $page.params.session_id;

  onMount(async () => {
    // Setup WebRTC
    peerConnection = new RTCPeerConnection();
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    localVideo.srcObject = stream;
    stream.getTracks().forEach(track => peerConnection.addTrack(track, stream));

    // Signaling via WebSocket or API (simulated)
    // Assume connection to backend WebSocket for signaling
  });

  onDestroy(() => {
    if (peerConnection) peerConnection.close();
  });
</script>

<div class="flex flex-col h-screen">
  <SessionTimer {session_id} />
  <div class="flex-1 grid grid-cols-2">
    <video bind:this={localVideo} autoplay playsinline muted></video>
    <video bind:this={remoteVideo} autoplay playsinline></video>
  </div>
</div>
