#!/usr/bin/env python3
"""فحص تزامن as3.py مع as3_app.py.

النسختان تشتركان في نواة التوليد (تهيئة البرنامج، دوال التصحيح الذكي،
العتبة، تنسيق المقاطع). أي تعديل في إحداهما يجب أن يصل للأخرى، وإلا فقد
يعطي `as3.py` برنامجًا مختلفًا عن `as3_app.py` بصمت (حدث فعلًا مع
`robot.settings`).

هذا السكربت يفشل (exit 1) إذا اختلفت إحدى الدوال المشتركة، ويطبع الفرق.
الاستثناء الوحيد المقصود هو `print_full_program` (علامات الالتقاط + النص
الإضافي في نسخة التطبيق).

التشغيل:  python3 tools/check_sync.py
"""

import difflib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SHARED = [
    "wait_for_release",
    "setup_lines",
    "estimated_threshold",
    "smart_helpers_lines",
    "format_seg",
    "merged_moves",
    "print_sensor",
    "push_action",
]
EXPECTED_DIFFERENT = {"print_full_program"}


def functions(path):
    """كل `def` في المستوى الأعلى مع جسمه فقط.

    لا نستخدم regex جشِعًا لأن آخر دالة في الملف كان يمتد جسمها إلى نهاية
    الملف (فيختلط بالبرنامج الرئيسي ويُعطي فروقًا وهمية). نتوقف عند أول
    سطر في العمود صفر ليس تعليقًا ولا `def` (أي كود التنفيذ الرئيسي).
    """
    lines = open(path, encoding="utf-8").read().split("\n")
    found = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("def "):
            name = line[4:line.index("(")]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.startswith("# ="):
                    break
                if nxt and not nxt[0].isspace() and not nxt.startswith("#") \
                        and not nxt.startswith("def "):
                    break
                if nxt.startswith("def "):
                    break
                j += 1
            found[name] = [l for l in lines[i:j] if l.strip()]
            i = j
        else:
            i += 1
    return found


def main():
    original = functions(os.path.join(ROOT, "as3.py"))
    app = functions(os.path.join(ROOT, "as3_app.py"))
    failures = 0

    for name in SHARED:
        if name not in original or name not in app:
            print("✗ الدالة %s غير موجودة في الملفين" % name)
            failures += 1
            continue
        a, b = original[name], app[name]
        if a == b:
            print("✓ %s" % name)
            continue
        failures += 1
        print("✗ %s مختلفة بين as3.py و as3_app.py:" % name)
        for line in difflib.unified_diff(a, b, "as3.py", "as3_app.py", lineterm="", n=1):
            print("   " + line)

    for name in sorted(EXPECTED_DIFFERENT):
        print("• %s مختلفة عمدًا (علامات الالتقاط/نص التطبيق)" % name)

    missing = sorted(set(SHARED + list(EXPECTED_DIFFERENT)) - (set(original) & set(app)))
    if missing:
        print("✗ دوال ناقصة: %s" % ", ".join(missing))
        failures += 1

    if failures:
        print("\nفشل فحص التزامن: انقل التعديل إلى الملفين معًا.")
        return 1
    print("\nكل الدوال المشتركة متزامنة ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
