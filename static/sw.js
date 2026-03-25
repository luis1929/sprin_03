// Colibry SW v2
const CACHE = 'colibry-v2';
const PRE   = ['/', '/status', '/static/icons/icon-192.png',
               '/static/icons/icon-512.png', '/static/manifest.json'];
const SKIP  = ['/ejecutar','/tts','/admin','/status','/qr.png',
               '/push/','/flowise','/health'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', e => {
  const p = new URL(e.request.url).pathname;
  if (SKIP.some(s => p.startsWith(s)) || e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then(hit => {
      const net = fetch(e.request).then(r => {
        if (r && r.status === 200 && r.type === 'basic')
          caches.open(CACHE).then(c => c.put(e.request, r.clone()));
        return r;
      }).catch(() => hit);
      return hit || net;
    })
  );
});

// ── Push Notifications ───────────────────────────────────────────────────
self.addEventListener('push', e => {
  let data = { title: 'Colibry', body: 'Nueva notificacion', icon: '/static/icons/icon-192.png' };
  try { data = { ...data, ...e.data.json() }; } catch {}
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body:    data.body,
      icon:    data.icon || '/static/icons/icon-192.png',
      badge:   '/static/icons/icon-192.png',
      vibrate: [200, 100, 200],
      tag:     data.tag || 'colibry-alert',
      data:    { url: data.url || '/status' },
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/status';
  e.waitUntil(clients.matchAll({ type: 'window' }).then(ws => {
    for (const w of ws) if (w.url.includes(url) && 'focus' in w) return w.focus();
    return clients.openWindow(url);
  }));
});
