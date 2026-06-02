"use client";

import { useEffect } from "react";

export function PwaRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") {
      return;
    }

    navigator.serviceWorker.getRegistrations()
      .then((registrations) => Promise.all(registrations.map((registration) => registration.unregister())))
      .catch(() => undefined);

    if ("caches" in window) {
      caches.keys()
        .then((keys) =>
          Promise.all(
            keys
              .filter((key) => key.startsWith("lucrandos-"))
              .map((key) => caches.delete(key)),
          ),
        )
        .catch(() => undefined);
    }
  }, []);

  return null;
}
