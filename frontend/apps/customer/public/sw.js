self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("lucrandos-"))
            .map((key) => caches.delete(key)),
        ),
      ),
      self.registration.unregister(),
    ]),
  );
  self.clients.claim();
});
