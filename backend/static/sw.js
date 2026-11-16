/* VILO PWA: offline cache restricted to public static UI only.
   Accounts/messages remain online-only and are never saved in SW cache. */
const CACHE='vilo-static-v05-iphone-1';
const ASSETS=['/static/style.css','/static/app.js','/static/vilo-icon.png','/static/favicon.png','/static/apple-touch-icon.png','/static/icon-192.png','/static/icon-512.png','/static/manifest.webmanifest'];
self.addEventListener('install', event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate', event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('vilo-static-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch', event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET' || url.origin!==self.location.origin || !ASSETS.includes(url.pathname)) return;
  event.respondWith(fetch(event.request).then(resp=>{
    if(resp.ok){const copy=resp.clone();caches.open(CACHE).then(c=>c.put(event.request,copy));}
    return resp;
  }).catch(()=>caches.match(event.request)));
});
