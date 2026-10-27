#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""رياضيات تحويل مسار نقطي (x, y) إلى أوامر «دوران ثم مستقيم».

هذا الملف يعمل على الكمبيوتر فقط (لا يستورد pybricks)، لذلك يمكن اختباره
بسهولة. النسخة التي تعمل على الـ Hub في ``xy_nav.py`` تستخدم نفس المعادلات
ونفس اصطلاح الإحداثيات.

الاصطلاح:
  * الأصل (0, 0) = نقطة البداية.
  * الزاوية 0 = اتجاه +X، والزيادة في الزاوية = دوران مع عقارب الساعة
    (وهو اصطلاح Pybricks: ``robot.turn(90)`` تدور يمينًا 90°).
  * +Y يقع على يمين الروبوت عندما يكون متجهًا نحو +X.
"""

from math import atan2, degrees, hypot


def wrap180(angle):
    """أعِد الزاوية إلى المدى [-180, 180)."""
    return (float(angle) + 180.0) % 360.0 - 180.0


def bearing(x1, y1, x2, y2):
    """زاوية الاتجاه من (x1,y1) إلى (x2,y2) بالدرجات."""
    return wrap180(degrees(atan2(y2 - y1, x2 - x1)))


def plan(waypoints, heading0=0.0, final_heading=None, tol=0.5):
    """حوّل قائمة نقاط إلى قائمة مقاطع ``("T", زاوية)`` / ``("S", مسافة)``.

    waypoints: قائمة ``(x, y)``. يُفترض أن الروبوت يبدأ من (0, 0).
    heading0: الاتجاه المطلق للروبوت عند البداية.
    final_heading: إن أُعطي، يُضاف دوران أخير لهذا الاتجاه.

    ملاحظة مهمة: هذه **خطة مفتوحة الحلقة** (open-loop). هي ممتازة للتجربة
    السريعة على سجادة التدريب، لكنها لا تصحّح انزلاق العجلات — استخدم
    ``xy_nav.py`` على الـ Hub للملاحة المغلقة الحلقة.
    """
    x, y = 0.0, 0.0
    heading = wrap180(heading0)
    legs = []
    for wp in waypoints:
        tx, ty = float(wp[0]), float(wp[1])
        dx, dy = tx - x, ty - y
        dist = hypot(dx, dy)
        if dist > tol:
            want = bearing(x, y, tx, ty)
            delta = wrap180(want - heading)
            if abs(delta) > tol:
                legs.append(("T", round(delta, 1)))
            legs.append(("S", round(dist, 1)))
            heading = want
        x, y = tx, ty
    if final_heading is not None:
        delta = wrap180(float(final_heading) - heading)
        if abs(delta) > tol:
            legs.append(("T", round(delta, 1)))
    return legs


def to_commands(legs, integer=True):
    """أوامر BLE الخام التي يفهمها محرك تنفيذ ConsoleReader: ``T 90`` / ``S 500``."""
    return ["%s %s" % (kind, int(round(value)) if integer else value)
            for kind, value in legs]


def to_python(legs, name="run", integer=True):
    """برنامج Python يفهمه محرّر ConsoleReader ويستطيع إرساله للـ Hub."""
    lines = ["def %s():" % name]
    for kind, value in legs:
        v = int(round(value)) if integer else value
        if kind == "T":
            lines.append("    robot.turn(%s)" % v)
        else:
            lines.append("    robot.straight(%s)" % v)
    if not legs:
        lines.append("    pass")
    lines += ["", "%s()" % name]
    return lines


def point_count(legs):
    """عدد الأوامر (كل نقطة = دوران + مستقيم كحد أقصى)."""
    return len(legs)
