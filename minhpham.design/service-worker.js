const CACHE_NAME = 'portfolio-cache-v1';
const urlsToCache = [
  'vendor.bundle5e48.js',
  'app.bundle5e48.js',
  'assets/fonts/4dd591d8-4168-4263-b05b-7183ddaff1f4.woff2'
  // Add other critical assets here
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});