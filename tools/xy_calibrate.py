# -*- coding: utf-8 -*-
"""
xy_calibrate.py — برنامج معايرة ميدانية لـ ``xy_nav.py`` على السجادة الحقيقية.

⚠️ هذا ملف **يُحمَّل على الـ Hub** عبر Pybricks Code (ليس سكربت كمبيوتر).
شغّله مرة واحدة قبل أول تشغيل تنافسي، وانسخ الأرقام التي يطبعها إلى
``xy_nav.py`` ثم إلى ``docs/تقرير_اختبار_xy_nav.md``.

لماذا؟ أثبتت محاكاة ``tools/xy_sim.py`` أن:
  * خطأ قطر العجلة +3% ⇒ ~54 مم خطأ على مسار 2.5 م،
  * انحراف الجيرو 0.5°/ث ⇒ ~113 مم خطأ (أكبر مصدر)،
  * وحتى مع معالم مثالية يبقى ~42 مم إن لم تُعاير العجلة.

هذا البرنامج يقيس الثلاثة بأدوات بسيطة: شريط قياس + عينك + زر واحد.

الاستخدام:
  1. ضع الروبوت على أرض بيضاء نظيفة، واترك أمامه مسافة ≥ 1.2 م.
  2. شغّل البرنامج وافتح سجل Pybricks (أو سجل تطبيق ConsoleReader).
  3. اتبع التعليمات المطبوعة؛ اضغط زر LEFT للمتابعة بين الخطوات.
  4. انسخ سطر ``# CALIB ...`` في تقريرك وعدّل الثوابت في ``xy_nav.py``.

القواعد: هذا البرنامج **للتدريب والمعايرة فقط** — لا تلمس الروبوت أثناء الجولة
الرسمية، وأطفئ البلوتوث/الواي فاي وشغّل ``xy_nav.py`` من الـ Hub مباشرة.
"""

from pybricks.hubs import PrimeHub
from pybricks.parameters import Button, Color, Direction, Port
from pybricks.pupdevices import ColorSensor, Motor
from pybricks.robotics import DriveBase
from pybricks.tools import wait

# ==== غيّر هذين الرقمين إلى ما تستنتجه من جدول التصحيح في الأسفل ====
WHEEL_MM = 56.0        # قطر العجلة الحالي المستخدم في xy_nav.py
AXLE_MM = 110.0        # المسافة بين مركزي العجلتين
TEST_DIST = 1000       # المسافة المأمور بها (مم)
GYRO_TURNS = 10        # عدد الدورات الكاملة لفحص انحراف الجيرو

hub = PrimeHub()
left_motor = Motor(Port.A, Direction.COUNTERCLOCKWISE)
right_motor = Motor(Port.B)
line_sensor = ColorSensor(Port.C)
robot = DriveBase(left_motor, right_motor, WHEEL_MM, AXLE_MM)
robot.use_gyro(True)
robot.settings(straight_speed=200, straight_acceleration=700,
               turn_rate=150, turn_acceleration=700)


def beep(ok=True):
    hub.speaker.beep(600 if ok else 200, 90)


def press_left(label):
    """انتظر ضغطة زر LEFT ثم أفلتَها — مع رسالة توضيحية."""
    print("# ▶ " + label)
    hub.light.on(Color.YELLOW)
    while Button.LEFT not in hub.buttons.pressed():
        wait(20)
    while hub.buttons.pressed():
        wait(20)
    hub.light.on(Color.GREEN)
    beep()


def measure_distance():
    """أمر 1000 مم ⇒ قِس بالشريط ⇒ استخدم الجدول لتصحيح قطر العجلة."""
    press_left("سيتحرك الروبوت 1000 مم للأمام — أبعِد ما حوله ثم اضغط LEFT")
    hub.imu.reset_heading(0)
    robot.reset()
    robot.straight(TEST_DIST)
    robot.stop()
    h = hub.imu.heading()
    print("# 1) أُمرت بـ %d مم. قِس المسافة الفعلية D بالشريط الآن." % TEST_DIST)
    print("#    انحراف الاتجاه أثناء المشي = %.2f° (يفضل < 2°)." % h)
    print("#    جدول تصحيح قطر العجلة (الحالي %.1f مم):" % WHEEL_MM)
    row = []
    for measured in range(970, 1031, 10):
        corrected = WHEEL_MM * TEST_DIST / measured
        row.append("%d⇒%.2f" % (measured, corrected))
    print("#    " + " | ".join(row))
    print("#    مثال: إن قِست 1030 مم فاكتب DriveBase(..., 54.37, 110).")
    print("#    ملاحظة: يطبع هذا الجدول تصحيحًا حسابيًا فقط — القياس عليك.")


def measure_gyro():
    """عشر دورات 360° يجب أن تُعيد الجيرو إلى الصفر تقريبًا."""
    press_left("سيدور الروبوت %d دورات كاملة في مكانه — اضغط LEFT" % GYRO_TURNS)
    hub.imu.reset_heading(0)
    for i in range(GYRO_TURNS):
        robot.turn(360)
        wait(150)
    drift = hub.imu.heading()
    # الصفر قد يظهر كـ ±360 بسبب الالتفاف
    while drift > 180:
        drift -= 360
    while drift < -180:
        drift += 360
    print("# 2) انحراف الجيرو بعد %d دورات = %.2f° ⇒ %.3f°/دورة"
          % (GYRO_TURNS, drift, drift / GYRO_TURNS))
    if abs(drift) < 2:
        print("#    ✓ الجيرو ممتاز — لا تحتاج إعادة ضبط بين المهام.")
    elif abs(drift) < 10:
        print("#    ⚠ انحراف مقبول لكن صفّر الجيرو عند كل خط مستقيم معروف.")
    else:
        print("#    ✗ انحراف كبير: افحص تثبيت الـ Hub والبطارية، واستخدم "
              "المحاذاة على خط قبل كل مهمة دقيقة.")


def measure_threshold():
    """عتاة الخط = منتصف قراءتي الأبيض والأسود تحت إضاءة القاعة."""
    press_left("ضع الحساس فوق الخلفية البيضاء (لا خط) ثم اضغط LEFT")
    samples = []
    for _ in range(7):
        samples.append(line_sensor.reflection())
        wait(20)
    white = sum(samples) / len(samples)

    press_left("الآن ضع الحساس فوق الخط الأسود تمامًا ثم اضغط LEFT")
    samples = []
    for _ in range(7):
        samples.append(line_sensor.reflection())
        wait(20)
    black = sum(samples) / len(samples)

    threshold = int((white + black) / 2)
    print("# 3) أبيض = %.1f | أسود = %.1f ⇒ LINE_THRESHOLD = %d"
          % (white, black, threshold))
    print("#    الفرق = %.1f (يفضل > 25؛ أقل من ذلك غيّر موضع الحساس أو الإضاءة)"
          % (white - black))
    if white - black < 25:
        print("#    ⚠ تباين ضعيف: حساسك مرتفع جدًا أو الإضاءة قوية — "
              "ستفشل find_line_and_snap() في المحاكاة أيضًا.")
    return threshold


def main():
    print("# ==== معايرة xy_nav.py — WRO 2026 ====")
    print("# حمّل هذا الملف مرة واحدة، وانسخ سطر CALIB في تقريرك.")
    print("# القيم الحالية: قطر العجلة %.1f مم | المسافة بين العجلتين %.1f مم"
          % (WHEEL_MM, AXLE_MM))
    beep()

    measure_distance()
    measure_gyro()
    threshold = measure_threshold()

    print("# ==== النتيجة ====")
    print("# CALIB wheel=%.2f axle=%.1f line_threshold=%d "
          "| غيّر DriveBase(...) و LINE_THRESHOLD في xy_nav.py"
          % (WHEEL_MM, AXLE_MM, threshold))
    print("# بعد التعديل شغّل: python3 tools/xy_sim.py --trials 30")
    print("# ثم كرّر المهمة 10 مرات على السجادة وسجّل سطر # FINAL.")
    hub.light.on(Color.BLUE)
    hub.speaker.beep(800, 200)


main()
