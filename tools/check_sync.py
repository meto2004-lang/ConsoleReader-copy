#!/usr/bin/env python3
"""فحص تزامن as3.py مع as3_app.py.

النسختان تشتركان في نواة التوليد (تهيئة البرنامج، دوال التصحيح الذكي،
العتبة، تنسيق المقاطع) **وفي ثوابت الروبوت**. أي تعديل في إحداهما يجب أن يصل
إلى الأخرى، وإلا فقد يعطي `as3.py` برنامجًا مختلفًا عن `as3_app.py` بصمت
(حدث فعلًا مع `robot.settings`).

هذا السكربت يفشل (exit 1) إذا اختلفت إحدى الدوال أو الثوابت المشتركة،
أو إذا عُرِّف ثابت مرتين في الملف نفسه. الاستثناء الوحيد المقصود هو
`print_full_program` (علامات الالتقاط + النص الإضافي في نسخة التطبيق).

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

# ثوابت تؤثر على البرنامج المولَّد — انحرافها يغيّر المسار بصمت.
SHARED_CONSTANTS = [
    "WHEEL_DIAMETER", "AXLE_TRACK",
    "MIN_DIST", "MIN_ANG", "MIN_ARM_ANG", "ARM_SPEED",
    "SEARCH_MARGIN", "MIN_SEARCH", "FOLLOW_GAIN", "ALIGN_SPEED",
    "FOLLOW_SIDE", "MOVE_ACCEL", "MOVE_TURN_ACCEL",
]

MAIN_MARKERS = ("# 5) البرنامج الرئيسي", "# 6) البرنامج الرئيسي")


def source_before_main(path):
    """نص الملف قبل الحلقة الرئيسية (لا ثوابت بعدها تُقارَن)."""
    text = open(path, encoding="utf-8").read()
    for marker in MAIN_MARKERS:
        if marker in text:
            return text[:text.index(marker)]
    return text


def functions(path):
    """كل `def` في المستوى الأعلى مع جسمه فقط.

    لا نستخدم regex جشِعًا لأن آخر دالة في الملف كان يمتد جسمها إلى نهاية
    الملف (فيختلط بالبرنامج الرئيسي ويُعطي فروقًا وهمية). نتوقف عند أول
    سطر في العمود صفر ليس تعليقًا ولا `def` (أي كود التنفيذ الرئيسي).
    """
    lines = source_before_main(path).split("\n")
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
            found[name] = [line for line in lines[i:j] if line.strip()]
            i = j
        else:
            i += 1
    return found


def constants(path):
    """قيم ثوابت المستوى الأعلى وعدد مرات تعريف كل منها."""
    values, counts = {}, {}
    pattern = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*([^#\n]+?)\s*(?:#.*)?$", re.M)
    for name, value in pattern.findall(source_before_main(path)):
        counts[name] = counts.get(name, 0) + 1
        if name not in values:
            values[name] = value.strip()
    return values, counts


def main():
    path_a = os.path.join(ROOT, "as3.py")
    path_b = os.path.join(ROOT, "as3_app.py")
    original, app = functions(path_a), functions(path_b)
    const_a, count_a = constants(path_a)
    const_b, count_b = constants(path_b)
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

    for name in SHARED_CONSTANTS:
        if name not in const_a or name not in const_b:
            print("✗ الثابت %s غير موجود في الملفين" % name)
            failures += 1
            continue
        if const_a[name] != const_b[name]:
            print("✗ الثابت %s مختلف: as3.py=%s | as3_app.py=%s"
                  % (name, const_a[name], const_b[name]))
            failures += 1
            continue
        if count_a[name] != 1 or count_b[name] != 1:
            print("✗ الثابت %s معرَّف أكثر من مرة (as3.py=%d, as3_app.py=%d)"
                  % (name, count_a[name], count_b[name]))
            failures += 1
            continue
        print("✓ %s = %s" % (name, const_a[name]))

    for name in sorted(EXPECTED_DIFFERENT):
        print("• %s مختلفة عمدًا (علامات الالتقاط/نص التطبيق)" % name)

    missing = sorted(set(SHARED + list(EXPECTED_DIFFERENT)) - (set(original) & set(app)))
    if missing:
        print("✗ دوال ناقصة: %s" % ", ".join(missing))
        failures += 1

    if failures:
        print("\nفشل فحص التزامن: انقل التعديل إلى الملفين معًا.")
        return 1
    print("\nكل الدوال والثوابت المشتركة متزامنة ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
