"""تحميل as3.py / as3_app.py على الكمبيوتر بلا هاردوير.

الفكرة: نقرأ الملف وننفّذ الجزء العلوي منه فقط (كل شيء قبل «البرنامج
الرئيسي»)، لأن الحلقة `while True` في الأسفل لا تنتهي. هكذا نستطيع اختبار
توليد البرنامج وآلة استلام الكود بدقة بينما نستخدم وحدات Pybricks وهمية.
"""

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stubs")
if STUBS not in sys.path:
    sys.path.insert(0, STUBS)

import hubclock  # noqa: E402  (بعد ضبط sys.path)


def _cut_before_main(src, marker):
    idx = src.index(marker)
    return src[: src.rindex("# ===", 0, idx)]


def load_hub_module(filename, marker="# 6) البرنامج الرئيسي"):
    """يعيد وحدة تحمل كل دوال الملف قبل البرنامج الرئيسي."""
    hubclock.reset_clock()
    path = os.path.join(ROOT, filename)
    with open(path, encoding="utf-8") as handle:
        src = handle.read()
    module = types.ModuleType(os.path.splitext(filename)[0])
    module.__dict__["__name__"] = "hub_under_test"
    exec(compile(_cut_before_main(src, marker), path, "exec"), module.__dict__)
    # MicroPython يوفّر gc.mem_free() — بايثون العادي لا يوفّرها.
    # نُبدّل الوحدة داخل الوحدة المحمَّلة حتى تعمل سطور التشخيص كما على الـ Hub.
    module.__dict__["gc"] = FakeGc()
    return module


class FakeGc:
    """بديل ``gc`` بسلوك MicroPython (mem_free) للاختبار على الكمبيوتر."""

    free = 20000

    def mem_free(self):
        return self.free

    def mem_alloc(self):
        return 0

    def collect(self):
        return None


def load_app():
    return load_hub_module("as3_app.py")


def load_original():
    return load_hub_module("as3.py", marker="# 5) البرنامج الرئيسي")


def feed(module, text):
    """يغذّي آلة أوامر الهاب بحرف حرف كما يفعل stdin."""
    for ch in text:
        module.handle_app_command(ch)
