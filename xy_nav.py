# -*- coding: utf-8 -*-
"""
xy_nav.py — طبقة ملاحة بإحداثيات (x, y) لسجادة WRO 2026 (Pybricks / SPIKE Prime).

الفكرة: بدل تسجيل «دُر 43° ثم امشِ 512 مم»، نقول للروبوت «اذهب إلى (900, 300)».
البرنامج يحسب الاتجاه والمسافة بنفسه، ويصحّح مساره أثناء الحركة بالجيروسكوب،
ويعيد ضبط مكانه عند كل خط/لون معروف على السجادة.

نظام الإحداثيات (ثبّته مرة واحدة ولا تغيّره):
  * الأصل (0, 0) = مركز منطقة البداية (المساحة البيضاء داخل الإطار الملون).
  * X بمحاذاة الضلع الطويل للسجادة (2362 مم)، موجب نحو داخل الملعب.
  * Y بمحاذاة الضلع القصير (1143 مم)، موجب نحو الحافة التي على يمين الروبوت
    عندما يكون متجهًا نحو +X (أي أن +Y = دوران +90° عن +X).
  * الزاوية 0 = اتجاه +X، والدوران الموجب = مع عقارب الساعة (اصطلاح Pybricks).

⚠️ هذا ملف **قالب/نموذج**: الإحداثيات في FIELD_MAP فارغة عمدًا. شغّل وضع
   MAP_MODE لقياس سجادتك الحقيقية، ثم املأها. لا تشغّل run() قبل ذلك.
⚠️ في المسابقة يجب أن يكون الروبوت مستقلًا تمامًا: حمّل هذا الملف على الـ Hub،
   وأوقف البلوتوث/الواي فاي، ولا تستخدم تطبيق ConsoleReader أثناء الجولة.

راجع docs/xy_navigation_wro2026.md للشرح الكامل وخطة المنافسة.

اختُبر هذا الملف بمحاكاة برمجية (tools/xy_sim.py — 270 محاولة) فوق عتاد وهمي
يُدخل انزلاق العجلات وانحراف الجيرو وضجيج الحساسات. النتيجة: المنطق سليم،
لكن الإحداثيات وحدها تراكم ~146 مم خطأ على مسار 2.5 م؛ لذلك قبل المنافسة:
  1) عاير قطر العجلة والجيرو بـ tools/xy_calibrate.py على سجادتك،
  2) ثبّت كلا المحورين على خطوط/ألوان معروفة قبل كل مهمة دقيقة،
  3) اجعل الرجل الأخيرة قصيرة.
التفاصيل في docs/تقرير_اختبار_xy_nav.md.
"""

from math import atan2, cos, degrees, radians, sin, sqrt

from pybricks.hubs import PrimeHub
from pybricks.parameters import Button, Color, Direction, Port
from pybricks.pupdevices import ColorSensor, Motor
from pybricks.robotics import DriveBase
from pybricks.tools import StopWatch, wait

# =========================================================
# 1) العتاد — نفس توصيلات مشروع ConsoleReader
# =========================================================
hub = PrimeHub()
left_motor = Motor(Port.A, Direction.COUNTERCLOCKWISE)
right_motor = Motor(Port.B)
arm_motor = Motor(Port.D)                 # محرك الذراع / المهام
line_sensor = ColorSensor(Port.C)         # حساس الألوان الوحيد في الروبوت الحالي
ARTIFACT_SENSOR = line_sensor             # إن أضفت حساسًا جانبيًا، اجعله هنا

robot = DriveBase(left_motor, right_motor, 56, 110)   # قطر العجلة / المسافة بين العجلتين
robot.use_gyro(True)
robot.settings(straight_speed=260, straight_acceleration=900,
               turn_rate=170, turn_acceleration=900)

# =========================================================
# 2) ثوابت قابلة للمعايرة
# =========================================================
FIELD_W, FIELD_H = 2362, 1143   # أبعاد سجادة WRO الرسمية (مم)

YAW0 = 0.0          # فرق بين محور الروبوت ومحور X للسجادة عند البداية (درجات)
X_MIN, X_MAX = -100, FIELD_W
Y_MIN, Y_MAX = -FIELD_H / 2, FIELD_H / 2

TOL_MM = 12         # نعتبر أننا وصلنا إذا بقي أقل من 12 مم
TURN_IN_PLACE = 25  # فوق هذا الانحراف، دُر في مكانك قبل التقدم (درجات)
KP_HEAD = 3.0       # معامل تصحيح الاتجاه أثناء المشي
KP_TURN = 2.5       # معامل الدوران في المكان
APPROACH_GAIN = 1.8 # كلما اقتربنا من الهدف خفّضنا السرعة
MIN_SPEED, MAX_SPEED = 70, 260     # مم/ث
TURN_RATE = 150                    # درجة/ث
LEG_TIMEOUT_MS = 9000              # مهلة لكل نقطة — يمنع التعليق
LINE_THRESHOLD = 30                # عتاة اكتشاف الخط الداكن (0..100)
LINE_TIMEOUT_MS = 2500             # مهلة البحث عن خط — يمنع التعليق عند تعطّل الحركة
SNAP_MAX_CORRECTION = 120          # أقصى تصحيح مقبول عند التثبيت (مم): أكبر = خط خاطئ
COLOR_SAMPLES = 7                  # تصويت بأغلبية القراءات للون
SCAN_HEADING = 90                  # اتجاه الروبوت عند قراءة لون القطع الأثرية
MAP_MODE = False                   #True = وضع قياس الإحداثيات باليد (للتدريب فقط)

# =========================================================
# 3) خريطة الملعب — ⚠️ املأها من وضع MAP_MODE قبل التشغيل
# =========================================================
# مثال بعد القياس:  "visitor_pickup": (250, 40),
FIELD_MAP = {
    "visitor_pickup":   None,   # (x, y) مكان الزوار
    "green_area":       None,   # منطقة الزائر الأخضر
    "museum_area":      None,   # المتحف / منطقة الزائر الأحمر
    "line_approach":    None,   # نقطة قريبة من خط أسود معروف للتصحيح
    "line_y":           None,   # قيمة Y الحقيقية لذلك الخط (رقم، وليس tuple)
    "tower_pickup":     None,   # أبراج حمراء
    "tower_target":     None,   # منطقة إعادة بناء الأبراج
    "cobblestone":      None,   # بداية مسار الكنس
}

ARTIFACT_SLOTS = [None, None, None, None]   # المربعات السوداء الأربعة في الحفريات
MUSEUM_SPOTS = {                            # منصات العرض حسب اللون
    "red": None, "green": None, "black": None, "blue": None, "yellow": None,
}
SWEEP_PATH = [None, None, None]             # خطوط مسح منطقة الغبار (مواقع عشوائية)

# لا نستخدم قاموسًا مفاتيحه Color: في MicroPython قد لا تكون ثوابت Color
# قابلة للتجزئة (hashable). سلسلة المقارنات أدناه آمنة دائمًا.

# =========================================================
# 4) دوال رياضية صغيرة
# =========================================================
def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _color_name(value):
    if value == Color.RED:
        return "red"
    if value == Color.GREEN:
        return "green"
    if value == Color.BLUE:
        return "blue"
    if value == Color.YELLOW:
        return "yellow"
    if value == Color.BLACK:
        return "black"
    if value == Color.WHITE:
        return "white"
    return "none"


def _is_point(value):
    """نقطة صالحة = زوج أرقام. يمنع TypeError أثناء الجولة بعد قياس خاطئ."""
    return (isinstance(value, (tuple, list)) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in value))


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _map_problems():
    """قائمة بمفاتيح FIELD_MAP الناقصة/غير الصالحة — فارغة = جاهز."""
    bad = []
    for key in ("visitor_pickup", "green_area", "museum_area",
                "line_approach", "tower_pickup", "tower_target", "cobblestone"):
        if not _is_point(FIELD_MAP.get(key)):
            bad.append(key)
    if not _is_number(FIELD_MAP.get("line_y")):
        bad.append("line_y")
    for i, slot in enumerate(ARTIFACT_SLOTS):
        if not _is_point(slot):
            bad.append("ARTIFACT_SLOTS[%d]" % i)
    for key, spot in MUSEUM_SPOTS.items():
        if not _is_point(spot):
            bad.append("MUSEUM_SPOTS[%s]" % key)
    for i, point in enumerate(SWEEP_PATH):
        if not _is_point(point):
            bad.append("SWEEP_PATH[%d]" % i)
    return bad


def _map_ready():
    return not _map_problems()


# =========================================================
# 5) طبقة الملاحة
# =========================================================
class Nav:
    """يحافظ على (x, y, heading) ويذهب إلى أي نقطة بحلقة تحكم مغلقة."""

    def __init__(self):
        self.x, self.y = 0.0, 0.0
        self.heading = _wrap(hub.imu.heading() + YAW0)
        # لا نستدعي robot.reset(): نعتمد على فرق المسافة، فلا نكسر العدّاد.
        self._last_d = robot.distance()

    def update(self):
        """حدّث الموقع من عدّاد المسافة + الجيروسكوب. تُستدعى كل دورة."""
        d = robot.distance()
        step = d - self._last_d
        self._last_d = d
        h = _wrap(hub.imu.heading() + YAW0)
        mid = radians(self.heading + _wrap(h - self.heading) / 2.0)
        self.x += step * cos(mid)
        self.y += step * sin(mid)
        self.heading = h
        return step

    def where(self):
        """الموقع الحالي (x, y, heading) — مفيد للتشخيص."""
        self.update()
        return (round(self.x), round(self.y), round(self.heading))

    def snap(self, axis=None, value=None, heading=None):
        """إعادة ضبط الموقع على معلم معروف (خط/لون/حافة) للقضاء على الانحراف المتراكم."""
        if axis == "x" and value is not None:
            self.x = float(value)
        if axis == "y" and value is not None:
            self.y = float(value)
        if heading is not None:
            self.heading = _wrap(heading)
        self._last_d = robot.distance()

    def face(self, target, tol=2, timeout_ms=3000):
        """دُر إلى اتجاه مطلق (0 = +X)."""
        watch = StopWatch()
        while watch.time() < timeout_ms:
            self.update()
            err = _wrap(target - self.heading)
            if abs(err) <= tol:
                robot.stop()
                return True
            robot.drive(0, _clamp(err * KP_TURN, -TURN_RATE, TURN_RATE))
            wait(10)
        robot.stop()
        return False

    def goto(self, tx, ty, tol=TOL_MM, timeout_ms=LEG_TIMEOUT_MS,
             backward=False, head=None):
        """اذهب إلى (tx, ty) — يحسب الاتجاه والمسافة ويصحّح أثناء الحركة.

        head: إن أُعطي، يدور الروبوت لهذا الاتجاه بعد الوصول (مهم للمناولة).
        backward: تحرك للخلف مع إبقاء مقدمة الروبوت نحو الهدف.
        """
        if not (X_MIN <= tx <= X_MAX and Y_MIN <= ty <= Y_MAX):
            print("# ⚠️ النقطة (%s, %s) خارج حدود السجادة" % (tx, ty))
            return False

        watch = StopWatch()
        while watch.time() < timeout_ms:
            self.update()
            dx, dy = tx - self.x, ty - self.y
            dist = sqrt(dx * dx + dy * dy)
            if dist <= tol:
                robot.stop()
                wait(30)              # المحرك لا يتوقف لحظيًا — احتسب مسافة التباطؤ
                self.update()
                if head is not None:
                    return self.face(head)
                return True

            err = _wrap(degrees(atan2(dy, dx)) - self.heading)
            if backward:
                err = _wrap(err + 180)
            if abs(err) > TURN_IN_PLACE:
                # انحراف كبير → دُر في مكانك أولًا (أدق من المشي أثناء الدوران)
                robot.drive(0, _clamp(err * KP_TURN, -TURN_RATE, TURN_RATE))
            else:
                speed = _clamp(dist * APPROACH_GAIN, MIN_SPEED, MAX_SPEED)
                speed *= max(0.2, 1.0 - abs(err) / 90.0)
                if backward:
                    speed = -speed
                robot.drive(speed, _clamp(err * KP_HEAD, -TURN_RATE, TURN_RATE))
            wait(10)

        robot.stop()
        hub.speaker.beep(180, 200)       # لم يصل: مهلة انتهت
        print("# ⚠️ لم أصل إلى (%s, %s)، آخر موقع %s" % (tx, ty, str(self.where())))
        return False

    def find_line_and_snap(self, axis, value, max_dist=250,
                           speed=80, direction=1,
                           timeout_ms=None, max_correction=None):
        """تقدّم ببطء حتى يرى الحساس خطًا داكنًا، ثم اعتبر إحداثي المحور = value.

        هذا هو «المرساة» الحقيقية: كل خط/حد لوني معروف على السجادة يلغي
        الانحراف المتراكم من عدّاد العجلات. كرّره قبل كل مهمة دقيقة.

        ``value`` يجب أن يكون إحداثي **حافة** الخط التي يطلق عندها الحساس
        (لا مركزه الهندسي): خط مركزه 1400 وعرضه 20 ⇒ الحافة 1390. استخدام
        المركز يُدخل خطأً ثابتًا بنصف عرض الخط — اكتُشف ذلك في المحاكاة.

        حمايتان أضافهما اختبار المحاكاة:
          * مهلة زمنية: لو تعطّلت الحركة (روبوت محشور) فإن عدّاد المسافة لا
            يتغيّر، فكانت الحلقة القديمة تدور إلى الأبد.
          * سقف للتصحيح: لو كان الحساس واقفًا أصلًا على خط آخر (تقاطع خطوط)،
            كان الروبوت يثبّت نفسه على بُعد 200 مم من مكانه الحقيقي. أي تصحيح
            أكبر من ``SNAP_MAX_CORRECTION`` يُرفض مع رسالة واضحة.
        """
        if timeout_ms is None:
            timeout_ms = LINE_TIMEOUT_MS
        if max_correction is None:
            max_correction = SNAP_MAX_CORRECTION
        d0 = robot.distance()
        watch = StopWatch()
        found = False
        while abs(robot.distance() - d0) < max_dist:
            if watch.time() > timeout_ms:
                robot.stop()
                self.update()
                print("# ⚠️ مهلة البحث عن الخط انتهت دون العثور عليه")
                return False
            if line_sensor.reflection() < LINE_THRESHOLD:
                found = True
                break
            # نُعيد إصدار الأمر كل دورة (أأمن على MicroPython)، ونُحدّث الموقع
            # أثناء الحركة بدل دمجه دفعة واحدة بعد التوقف.
            robot.drive(direction * speed, 0)
            self.update()
            wait(10)
        robot.stop()
        self.update()
        if found and axis in ("x", "y"):
            current = self.x if axis == "x" else self.y
            delta = float(value) - current
            if abs(delta) > max_correction:
                print("# ⚠️ رُفض تثبيت %s=%s: التصحيح %d مم > الحدّ %d مم"
                      " (غالبًا خط آخر أو قراءة خاطئة)"
                      % (axis, str(value), round(delta), max_correction))
                return False
            self.snap(axis, value)
        return found

    def read_color(self, samples=COLOR_SAMPLES):
        """اقرأ لون جسم بتصويت أغلبية — يقاوم اختلاف الإضاءة وظل الحكّام."""
        counts = {}
        for _ in range(samples):
            name = _color_name(ARTIFACT_SENSOR.color())
            if name != "none":
                counts[name] = counts.get(name, 0) + 1
            wait(20)
        best, best_n = "none", 0
        for name in counts:
            if counts[name] > best_n:
                best, best_n = name, counts[name]
        return best


# =========================================================
# 6) وضع القياس: ادفع الروبوت باليد واطبع إحداثيات كل معلم
# =========================================================
def map_points():
    """شغّل هذا في التدريب فقط: ادفع الروبوت باليد، اضغط الزر الأيسر، انسخ السطر.

    ملاحظة قانونية: هذا الوضع للتدريب/المعايرة فقط، ولا يجوز لمس الروبوت
    أثناء الجولة الرسمية. انسخ القيم إلى FIELD_MAP ثم أعد MAP_MODE = False.
    """
    nav = Nav()
    print("# XY_MAP_READY — ادفع الروبوت باليد إلى المعلم، ثم اضغط الزر الأيسر")
    print("# كل سطر: # P <x> <y> <heading>")
    while True:
        nav.update()
        if Button.LEFT in hub.buttons.pressed():
            print("# P %d %d %d" % (round(nav.x), round(nav.y), round(nav.heading)))
            hub.speaker.beep(600, 80)
            while hub.buttons.pressed():
                wait(10)
        wait(20)


# =========================================================
# 7) برنامج السباق — هيكل مقترح (عدّل الميكانيكا حسب روبوتك)
# =========================================================
def run():
    nav = Nav()

    def must(ok, name):
        """تنقّل حرج: فشله يعني أن الروبوت تائه — التوقف أأمن من المتابعة."""
        if not ok:
            print("# ⚠️ فشل التنقّل إلى %s — إيقاف الجولة، آخر موقع %s"
                  % (name, str(nav.where())))
        return bool(ok)

    problems = _map_problems()
    if problems:
        hub.speaker.beep(150, 300)
        print("# ⚠️ FIELD_MAP غير مكتمل/غير صالح: %s — شغّل MAP_MODE واملأه أولاً"
              % ", ".join(problems))
        return

    hub.light.on(Color.GREEN)

    # أ) مهام بإحداثيات ثابتة: الزوار (مواقعهم لا تتغير عشوائيًا).
    if not nav.goto(FIELD_MAP["visitor_pickup"][0],
                    FIELD_MAP["visitor_pickup"][1], head=0):
        return
    arm_motor.run_angle(300, 90)          # مثال: التقاط — استبدل بآليتك
    if not nav.goto(FIELD_MAP["green_area"][0], FIELD_MAP["green_area"][1]):
        return
    arm_motor.run_angle(300, -90)         # مثال: إفلات

    # ب) إعادة ضبط الموضع على خط معروف قبل المناولة الدقيقة.
    if not must(nav.goto(FIELD_MAP["line_approach"][0],
                         FIELD_MAP["line_approach"][1]), "line_approach"):
        return
    if nav.find_line_and_snap("y", FIELD_MAP["line_y"]):
        hub.light.on(Color.GREEN)
    else:
        hub.speaker.beep(250, 150)        # لم نجد الخط — تابع بحذر

    # ج) الأبراج: مواقع ثابتة → إحداثيات مباشرة.
    if not must(nav.goto(FIELD_MAP["tower_pickup"][0],
                         FIELD_MAP["tower_pickup"][1]), "tower_pickup"):
        return
    if not must(nav.goto(FIELD_MAP["tower_target"][0],
                         FIELD_MAP["tower_target"][1]), "tower_target"):
        return

    # د) القطع الأثرية: 4 من 5 بألوان عشوائية الترتيب → اقرأ اللون ثم اختر الوجهة.
    for slot in ARTIFACT_SLOTS:
        if not nav.goto(slot[0], slot[1], head=SCAN_HEADING):
            continue
        colour = nav.read_color()
        spot = MUSEUM_SPOTS.get(colour)
        if spot is None:
            hub.speaker.beep(220, 80)     # لون غير متوقع: تخطّ ولا تُخاطر
            continue
        arm_motor.run_angle(300, 90)      # التقط القطعة
        if nav.goto(spot[0], spot[1]):
            arm_motor.run_angle(300, -90)  # ضعها في منصة اللون المطابق

    # هـ) جزيئات الغبار: مواقعها عشوائية → لا إحداثيات ثابتة، بل مسح شامل.
    for point in SWEEP_PATH:
        nav.goto(point[0], point[1])

    # و) العودة / إنهاء: سطر واحد يفيدك في تشخيص الانحراف بعد الجولة.
    print("# FINAL %s" % str(nav.where()))
    hub.light.on(Color.BLUE)


# ==== 8) البرنامج الرئيسي — لا تُستدعى في الاختبارات (تُقطع قبل هذا السطر) ====
if MAP_MODE:
    map_points()
else:
    run()
