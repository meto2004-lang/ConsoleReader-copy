#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""حوّل نقاط (x, y) إلى برنامج يفهمه ConsoleReader.

أمثلة:
    python3 tools/xy_to_commands.py 0,0 300,0 300,400 1000,400
    python3 tools/xy_to_commands.py 0,0 300,0 300,400 --ble
    python3 tools/xy_to_commands.py --file waypoints.json --python --out race_program.py

ملف waypoints.json يمكن أن يكون:
    [[0, 0], [300, 0], [300, 400]]
أو:
    {"visitor_pickup": [250, 40], "green_area": [900, 300]}

تحذير: الناتج مسار مفتوح الحلقة (turn + straight). استخدمه للتجربة السريعة،
أما في المسابقة فاستخدم ``xy_nav.py`` مع تصحيح بالخطوط/الألوان.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xy_math import plan, to_commands, to_python  # noqa: E402


def parse_point(text):
    parts = text.replace("،", ",").split(",")
    if len(parts) < 2:
        raise ValueError("النقطة يجب أن تكون بالشكل x,y — استلمت: %s" % text)
    return (float(parts[0]), float(parts[1]))


def read_points(args):
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return [(v[0], v[1]) for v in data.values()]
        return [(v[0], v[1]) for v in data]
    return [parse_point(p) for p in args.points]


def main():
    ap = argparse.ArgumentParser(
        description="تحويل إحداثيات (x,y) إلى أوامر حركة — الأصل (0,0) = نقطة البداية")
    ap.add_argument("points", nargs="*", help="نقاط مثل: 300,0 300,400")
    ap.add_argument("--file", help="ملف JSON بقائمة النقاط أو قاموس بأسمائها")
    ap.add_argument("--heading0", type=float, default=0.0,
                    help="اتجاه الروبوت عند البداية بالدرجات (0 = نحو +X)")
    ap.add_argument("--final", type=float, default=None,
                    help="اتجاه نهائي يُضاف في آخر المسار")
    ap.add_argument("--ble", action="store_true",
                    help="إخراج أوامر T/S الخام بدل برنامج Python")
    ap.add_argument("--python", action="store_true",
                    help="إخراج برنامج Python (وهو الافتراضي)")
    ap.add_argument("--out", help="احفظ الناتج في ملف بدل الطباعة فقط")
    ap.add_argument("--max-commands", type=int, default=90,
                    help="حد Hub في ConsoleReader (RUN_MAX_LINES = 90)")
    args = ap.parse_args()

    if not args.file and not args.points:
        ap.error("أعطِ نقاطًا أو استخدم --file")

    points = read_points(args)
    legs = plan(points, args.heading0, args.final)

    if args.ble:
        body = to_commands(legs)
    else:
        body = to_python(legs)

    header = [
        "# مسار مولّد من إحداثيات (x, y) — الأصل (0,0) = نقطة البداية",
        "# 0 درجة = اتجاه +X، والدوران الموجب = يمين/مع عقارب الساعة",
        "# عدد النقاط: %d — عدد الأوامر: %d" % (len(points), len(legs)),
        "# ⚠️ مسار مفتوح الحلقة: عايِر قطر العجلة وصحّح بالخطوط/الألوان قبل المسابقة",
    ]
    text = "\n".join(header + body) + "\n"

    if len(legs) > args.max_commands:
        print("⚠️ عدد الأوامر %d يتجاوز حد الـ Hub (%d) — قسّم المسار إلى برنامجين."
              % (len(legs), args.max_commands), file=sys.stderr)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
        print("✓ كُتب %s (%d أمر)" % (args.out, len(legs)))
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
