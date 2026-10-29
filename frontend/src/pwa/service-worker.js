/* The build replaces these two placeholders with a content hash and exact public URLs. */
const CACHE = 'word-guess-shell-__CACHE_ID__'
const SHELL = __SHELL_FILES__
const FILES = new Set(SHELL)
const isPage = (path) => path === '/' || /^\/play\/(4|5|6|campaign)\/?$/.test(path)
  || /^\/(modes|shop|campaign|collection|leaderboards|chests)\/?$/.test(path)
  || /^\/chests\/[a-f0-9-]{36}\/?$/.test(path)

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(
    SHELL.map((url) => new Request(url, { cache: 'reload', credentials: 'omit' })),
  )))
  // Updates wait for an explicit request or for every old window to close.
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(keys.filter((key) => key.startsWith('word-guess-shell-') && key !== CACHE).map((key) => caches.delete(key)))
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return
  if (request.mode === 'navigate' && isPage(url.pathname)) {
    event.respondWith(caches.open(CACHE).then((cache) => cache.match('/index.html')).then((response) => response || fetch(request)))
  } else if (!url.search && FILES.has(url.pathname)) {
    event.respondWith(caches.open(CACHE).then((cache) => cache.match(url.pathname)).then((response) => response || fetch(request)))
  }
  // Audio is opt-in and API/private data never enters CacheStorage or a retry queue.
})

self.addEventListener('message', (event) => {
  if (event.data?.type !== 'APPLY_UPDATE') return
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    if (windows.length !== 1 || windows[0].id !== event.source?.id) {
      event.source?.postMessage({ type: 'UPDATE_BLOCKED' })
      return
    }
    await self.skipWaiting()
  })())
})
