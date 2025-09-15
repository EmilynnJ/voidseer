import { build, files, version } from '$service-worker';

// Create a unique cache name for this deployment
const CACHE = `cache-${version}`;

const ASSETS = [
  ...build, // the built files
  ...files, // everything in `static`
];

// Install event - cache all static assets
self.addEventListener('install', (event) => {
  // Create a new cache and add all files to it
  async function addFilesToCache() {
    const cache = await caches.open(CACHE);
    await cache.addAll(ASSETS);
  }

  event.waitUntil(addFilesToCache());
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  // Remove previous cached data if it exists
  async function deleteOldCaches() {
    for (const key of await caches.keys()) {
      if (key !== CACHE) await caches.delete(key);
    }
  }

  event.waitUntil(deleteOldCaches());
});

// Fetch event - serve from cache, falling back to network
self.addEventListener('fetch', (event) => {
  // Skip cross-origin requests, like those to Google Analytics
  if (!(event.request.url.startsWith('http') || event.request.url.startsWith('https'))) return;
  if (event.request.method !== 'GET') return;

  async function respond() {
    const url = new URL(event.request.url);
    const cache = await caches.open(CACHE);

    // Serve build/static files from cache first
    if (ASSETS.includes(url.pathname)) {
      const cachedResponse = await cache.match(event.request);
      if (cachedResponse) return cachedResponse;
    }

    // For API requests, try network first, then cache
    try {
      const response = await fetch(event.request);

      // If the response is good, cache it
      if (response.status === 200) {
        cache.put(event.request, response.clone());
      }

      return response;
    } catch (error) {
      // If network fails, try to serve from cache
      const cachedResponse = await cache.match(event.request);
      if (cachedResponse) return cachedResponse;

      // If no cache, return an offline page
      if (event.request.mode === 'navigate') {
        return cache.match('/offline.html');
      }

      throw error;
    }
  }

  event.respondWith(respond() as Promise<Response>);
});

// Push notification event listener
self.addEventListener('push', (event) => {
  if (!event.data) return;

  const data = event.data.json();
  const title = data.title || 'SoulSeer';
  const options = {
    body: data.body || 'You have a new notification',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/',
    },
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  // Handle the notification click
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      // If a window is already open, focus it
      for (const client of clientList) {
        if (client.url === event.notification.data.url && 'focus' in client) {
          return client.focus();
        }
      }
      
      // Otherwise, open a new window
      if (clients.openWindow) {
        return clients.openWindow(event.notification.data.url);
      }
    })
  );
});

// Handle background sync
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-messages') {
    // Handle background sync for messages
    // This is a placeholder - implement your own sync logic
    console.log('Background sync for messages');
  }
});

// Handle periodic sync (for background updates)
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'update-readers') {
    // Handle periodic updates
    // This is a placeholder - implement your own update logic
    console.log('Periodic sync for readers');
  }
});

// Handle push subscription change (for push notifications)
self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil(
    Promise.resolve().then(async () => {
      // This is a placeholder - implement your own subscription update logic
      console.log('Push subscription changed');
    })
  );
});
