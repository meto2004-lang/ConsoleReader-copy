/* ConsoleReader — Service Worker
   الهدف: أن تفتح الصفحة في الميدان حتى بلا إنترنت، وتتحدّث تلقائيًا عند توفر اتصال.
   كل المسارات نسبية لأن الصفحة قد تُقدَّم من مسار فرعي (GitHub Pages: /<repo>/app/).

   ملاحظة مهمة (خطأ سابق): طلبات التنقّل (navigate) تُخدَم من النسخة المخزّنة
   تحت "./index.html"، بينما كان التحديث يُكتب تحت عنوان الطلب نفسه ("/app/").
   النتيجة أن نسخة الصفحة المخزّنة لم تُستبدل أبدًا. الحل: كل تنقّل يحدّث
   أيضًا مفتاح "./index.html"، مع ترقية اسم الذاكرة في كل إصدار كشبكة أمان.

   إصلاح إضافي (2026-10-27): كان طلب `../as3_app.py?v=<timestamp>` يُخزَّن
   تحت عنوانه الكامل في كل مرة، فتتراكم نسخ 82KB بلا حدّ داخل نفس الذاكرة.
   الآن: مفتاح ثابت واحد لملف الـ Hub، وتنظيف المفاتيح القديمة عند التفعيل،
   وتجريد `?v=` من مفاتيح التخزين لبقية الأصول.
*/

const CACHE = "consolereader-v15";

// مفتاح ثابت لملف كود الـ Hub (نسخة واحدة فقط مهما اختلف ?v=).
const PY_URL = new URL("../as3_app.py", self.registration.scope).href;

const ASSETS = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png"
];

// التثبيت: نخزّن كل ما تحتاجه الصفحة حتى تعمل دون إنترنت.
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

// التفعيل: نحذف ذاكرة النسخ القديمة، ثم ننظّف مفاتيح ?v= المتراكمة قديمًا.
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => caches.open(CACHE))
      .then((c) => c.keys().then((reqs) => Promise.all(
        reqs.filter((r) => r.url.includes("as3_app.py?v=")).map((r) => c.delete(r))
      )))
      .then(() => self.clients.claim())
  );
});

function cacheKeyFor(request, isNavigate, isPy) {
  if (isNavigate) return "./index.html";
  if (isPy) return PY_URL;
  // عناوين كسر الذاكرة لا تُخزَّن تحت مفاتيح لا نهائية.
  if (request.url.includes("?v=")) return request.url.split("?")[0];
  return request;
}

/* الجلب: لطلبات التنقّل وملفات .py نجلب النسخة الأحدث من الشبكة أولًا مع
   الرجوع للذاكرة عند انقطاع الإنترنت. */
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const isNavigate = e.request.mode === "navigate";
  const isPy = e.request.url.includes(".py");
  const cachedKey = cacheKeyFor(e.request, isNavigate, isPy);
  e.respondWith(respond(cachedKey, e.request, isNavigate, isPy));
});

async function respond(cachedKey, original, isNavigate, isPy) {
  const cached = await caches.match(cachedKey, { ignoreSearch: true });

  const updating = fetch(original)
    .then((res) => {
      if (res && res.status === 200 && res.type === "basic") {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(cachedKey, copy)).catch(() => {});
        if (isNavigate) {
          const copy2 = res.clone();
          caches.open(CACHE).then((c) => c.put(original, copy2)).catch(() => {});
        }
      }
      return res;
    })
    .catch(() => null);

  if (isNavigate || isPy) {
    const net = await updating;
    if (net) return net;
  }

  if (cached) return cached;

  const net = await updating;
  return net || new Response("Offline", {
    status: 503,
    statusText: "Offline",
    headers: { "Content-Type": "text/plain; charset=utf-8" }
  });
}
