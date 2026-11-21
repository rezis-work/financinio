const CACHE_NAME = 'financinio-shell-v1';
const SHELL_ASSETS = ['/manifest.webmanifest', '/icon.svg'];

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE_NAME)
			.then((cache) => cache.addAll(SHELL_ASSETS))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) =>
				Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
			)
			.then(() => self.clients.claim())
	);
});

self.addEventListener('fetch', (event) => {
	const { request } = event;
	if (request.method !== 'GET') return;
	const url = new URL(request.url);
	// Never cache API calls or cross-origin requests
	if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

	event.respondWith(
		fetch(request).catch(() => caches.match(request))
	);
});
