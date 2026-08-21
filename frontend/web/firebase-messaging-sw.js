/* eslint-disable no-undef */
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: 'AIzaSyDCiEZujCfINIj9uFRZgqRD8GSJgOo3NJ8',
  authDomain: 'sylo-e895e.firebaseapp.com',
  projectId: 'sylo-e895e',
  storageBucket: 'sylo-e895e.firebasestorage.app',
  messagingSenderId: '737107826319',
  appId: '1:737107826319:web:11d3ea5dcf57f18e5942fa',
  measurementId: 'G-ZR0R5W45N5',
});

const messaging = firebase.messaging();

function extractData(data) {
  if (!data) return {};
  return data;
}

function resolveThreadId(data) {
  return (
    data.thread_id ||
    data.meta_thread_id ||
    ''
  );
}

function buildClickUrl(data) {
  const threadId = resolveThreadId(data);
  if (threadId) {
    return `/#/chat?threadId=${encodeURIComponent(threadId)}`;
  }
  return '/#/';
}

messaging.onBackgroundMessage((payload) => {
  const data = extractData(payload.data);
  const title = payload.notification?.title || 'Sylo';
  const body = payload.notification?.body || 'You have a new update';
  const options = {
    body,
    data,
    icon: '/icons/Icon-192.png',
    badge: '/icons/Icon-192.png',
    tag: resolveThreadId(data) || 'sylo-notification',
  };

  self.registration.showNotification(title, options);
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const data = extractData(event.notification?.data || {});
  const targetUrl = buildClickUrl(data);

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ('focus' in client) {
          if ('navigate' in client) {
            client.navigate(targetUrl);
          }
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
      return null;
    })
  );
});

