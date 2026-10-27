"""خادم تطوير صغير للـ PWA — بديل ``python -m http.server``.

لماذا لا يكفي الخادم القياسي؟
  * ``http.server`` من جذر المشروع يعرض قائمة ملفات على ``/`` بدل التطبيق.
  * المتصفحات تخزّن ``index.html`` و``sw.js``، فترى نسخة قديمة أثناء التطوير
    (وهي نفس مشكلة P1‑1 التي أُصلحت في ``sw.js``). هنا نُرسل ``no-store``
    لملفات التطبيق حتى يظهر كل تعديل فورًا بعد التحديث.

الاستخدام:
    python tools/dev_server.py            # 0.0.0.0:8000، يفتح /app/
    python tools/dev_server.py --port 8080
    python tools/dev_server.py --host 127.0.0.1   # محلي فقط

يبقى ``python -m http.server`` كافيًا للنشر اليدوي؛ هذا الملف للتطوير والمعاينة.
"""

import argparse
import functools
import http.server
import os
import socketserver

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NO_STORE = (".html", ".js", ".json", ".webmanifest")


class Handler(http.server.SimpleHTTPRequestHandler):
    """جذر المشروع + إعادة توجيه ``/`` إلى ``/app/`` + منع التخزين المؤقت."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):                     # noqa: N802 (اسم من مكتبة بايثون)
        if self.path in ("/", "/index.html"):
            # التطبيق الفعلي في /app/ وليس في جذر المستودع
            self.send_response(302)
            self.send_header("Location", "/app/")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        super().do_GET()

    def end_headers(self):
        path = self.path.lower().split("?")[0]
        # "/app/" مسار مجلد يُقدَّم كـ index.html — يجب ألا يُخزَّن أيضًا
        if path.endswith("/") or path.endswith(NO_STORE):
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        # سجل مختصر: بلا ضجيج عناوين IP في كل طلب
        print("[dev] " + (fmt % args))


def main():
    ap = argparse.ArgumentParser(description="خادم معاينة ConsoleReader PWA")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--host", default="0.0.0.0",
                    help="0.0.0.0 للوصول من الجوال/المعاينة، 127.0.0.1 للمحلي فقط")
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(ROOT, "app", "index.html")):
        raise SystemExit("لم أجد app/index.html بجانب مجلد tools — شغّله من المستودع")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((args.host, args.port), Handler) as httpd:
        httpd.daemon_threads = True
        print("خادم التطوير يعمل: http://%s:%d/app/" % (args.host, args.port))
        print("(الجذر / يعيد التوجيه إلى /app/ — أوقفه بـ Ctrl+C)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nأُوقف الخادم")


if __name__ == "__main__":
    main()
