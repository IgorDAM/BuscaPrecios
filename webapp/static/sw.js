// Service worker mínimo: solo lo necesario para que el navegador
// considere la app "instalable" como PWA.
//
// Estrategia "red primero, caché como respaldo": si hay conexión, siempre
// se sirve la versión más reciente de la interfaz (antes era al revés, y
// el navegador se quedaba ejecutando un app.js viejo aunque el servidor
// ya tuviera uno nuevo). La caché solo entra en juego si estás sin red.

const CACHE = "comparasuper-v2";
const ARCHIVOS_ESTATICOS = ["/", "/style.css", "/app.js", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ARCHIVOS_ESTATICOS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Borrar cachés de versiones anteriores, si no el navegador puede
  // seguir sirviendo archivos antiguos indefinidamente.
  event.waitUntil(
    caches
      .keys()
      .then((claves) =>
        Promise.all(claves.filter((c) => c !== CACHE).map((c) => caches.delete(c)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Las llamadas a la API nunca se cachean: precios siempre en vivo.
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((respuesta) => {
        const copia = respuesta.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copia));
        return respuesta;
      })
      .catch(() => caches.match(event.request))
  );
});
