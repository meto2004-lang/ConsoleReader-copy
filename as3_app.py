# برنامج التدريب - نسخة التطبيق (as3_app.py)
# نفس as3.py، لكن يمكن التحكم فيه من تطبيق الويب (app/index.html) عبر البلوتوث
# بدلاً من أزرار الروبوت فقط. أزرار الروبوت ما زالت تعمل كالمعتاد.
# أوامر التطبيق (حرف واحد): R=تسجيل حركة، L=قراءة حساسات، C=طباعة البرنامج،
# F=نقطة خط ذكية، T=متابعة خط، U=تراجع.
# التحكم عن بعد (أزرار الأسهم): w=للأمام s=للخلف a=لف يسارًا d=لف يمينًا x=إيقاف.
# إرسال الكود من التطبيق: B=بدء الاستلام بالحزم ثم حزم N (بايتان طول + بيانات)
#   ثم E=انتهى، و G=نفّذ الكود المستلم الآن، و x=إيقاف التنفيذ.
#   (الوضع القديم K … أسطر … E ما زال مدعومًا.)
# نبضة الحياة أثناء التنفيذ: p=نبضة (تفعّل المراقب)، q=أوقفه (يُستخدم عند
#   إخفاء الصفحة كي لا تتوقف بسبب تقييد مؤقتات المتصفح).
# عتاة الخط من التطبيق: H ثم الرقم ثم سطر جديد (مثال: "H 49\n").
# نسخة الـ Hub تُطبع عند البدء: HUB_VERSION
# مكتبة برامج على الـ Hub (v9): W <اسم> = احفظ البرنامج المستلم، V = اعرض القائمة،
#   J <رقم> = شغّل برنامجًا محفوظًا، D <رقم> = احذفه. التخزين في RAM (تُفقد
#   البرامج بإعادة تشغيل الـ Hub) — النسخة الدائمة في مكتبة التطبيق.

from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, ColorSensor
from pybricks.parameters import Port, Button, Direction, Color
from pybricks.robotics import DriveBase
from pybricks.tools import wait, StopWatch

# مدخل قياسي لاستقبال أوامر تطبيق الويب عبر البلوتوث (Pybricks stdin)
from usys import stdin
from uselect import poll

# لقياس الذاكرة الحرة عند البدء (تشخيص فقط)
import gc

# =========================================================
# 1) المنافذ حسب روبوتك
# =========================================================
hub = PrimeHub()

left_motor  = Motor(Port.A, Direction.COUNTERCLOCKWISE)  # عدّل الاتجاه إذا لزم
right_motor = Motor(Port.B)

# محرك إضافي (ذراع / بوابة / مهام) على المنفذ D
ARM_PORT        = Port.D
ARM_PORT_LETTER = "D"          # يُطبع في البرنامج الناتج
try:
    arm_motor = Motor(ARM_PORT)
except Exception:
    arm_motor = None

def get_arm():
    # يعيد كائن محرك المنفذ D، ويحاول تهيئته مجددًا إن وُصل السلك بعد بدء البرنامج
    global arm_motor
    if arm_motor is None:
        try:
            arm_motor = Motor(ARM_PORT)
            arm_motor.stop()
            arm_motor.reset_angle(0)
        except Exception:
            arm_motor = None
    return arm_motor

# حساس ألوان واحد فقط، مركّب على المنفذ C.
#   كل القراءات (عتبة الخط، البحث عن الخط، المحاذاة، متابعة الحافة) تعتمد
#   على هذا الحسّاس وحده — لا يوجد حسّاس ألوان على D. غيّر LINE_PORT فقط إن كان
#   الحسّاس في منفذ آخر.
LINE_PORT        = Port.C
LINE_PORT_LETTER = "C"          # نفس المنفذ أعلاه — يُطبع في البرنامج الناتج
line_sensor = ColorSensor(LINE_PORT)

# =========================================================
# 2) أبعاد الروبوت (عدّلها لاحقاً للمعايرة الدقيقة)
# =========================================================
WHEEL_DIAMETER = 56
AXLE_TRACK     = 110

robot = DriveBase(left_motor, right_motor, WHEEL_DIAMETER, AXLE_TRACK)
robot.use_gyro(True)  # نفس إعداد برنامج السباق (جيرو مفعّل)

# إصدار برنامج الـ Hub — يظهر في سجل التطبيق ليعرف المستخدم أن النسخة محدَّثة
HUB_VERSION = "9"

# عتبات دنيا تتجاهل اهتزاز اليد
MIN_DIST    = 5    # أقل من 5 مم = ضجيج
MIN_ANG     = 2    # أقل من درجتين = ضجيج
MIN_ARM_ANG = 5    # أقل من 5 درجات على محرك المنفذ D = ضجيج
ARM_SPEED   = 300  # سرعة محرك المنفذ D في البرنامج الناتج (deg/s)

# إعدادات التصحيح الذكي
SEARCH_MARGIN = 50   # هامش بحث إضافي بعد المسافة المجرَّبة (مم)
MIN_SEARCH    = 80   # أدنى مسافة بحث عن الخط
FOLLOW_GAIN   = 2.5  # معامل التحكم P لمتابعة الخط
ALIGN_SPEED   = 25   # سرعة الدوران للمحاذاة (deg/s)

# بالحسّاس الواحد لا يمكن استنتاج «أي حافة» نتبع من مقارنة حساسين،
# فالجانب يُثبَّت هنا: "L" يصحّح نحو اليسار، "R" نحو اليمين.
# اقلبه إذا كان الروبوت يبتعد عن الخط بدل أن يلتصق بحافته.
FOLLOW_SIDE   = "L"

# تسارع الحركات في برنامج السباق الناتج (نعومة أثناء التشغيل)
MOVE_ACCEL      = 1200
MOVE_TURN_ACCEL = 1500

# =========================================================
# 3) سجلات التدريب
# =========================================================
# كل عملية تسجيل تُخزَّن كعنصر رباعي:
#   ("move",   [قطع المسار], آخر مسافة قبل التسجيل, آخر زاوية قبل التسجيل)
#   ("sensor", [أسطر القراءات], None, None)
# قطع المسار: ("turn", زاوية) ("straight", مسافة)
#             ("find_line", (اتجاه, أقصى مسافة)) ("align_line", سرعة)
#             ("follow_line", (مسافة, جانب))
# حفظ "المرجع السابق" داخل العنصر يسمح للتراجع بإعادته بدقة.
actions = []

# نطاق الانعكاس (أظلم وأفتح قياس) لحساب عتاة الخط تلقائيًا.
#   في السابق كانت تُخزَّن كل العينات في قائمة (حتى 400 عنصر ≈ 3.2KB)،
#   وذاكرة الـ Hub ضيقة جدًا. لا نحتاج لحساب العتبة إلا أصغر قيمة وأكبرها،
#   فحفظهما فقط يوفّر الذاكرة ويُلغي كلفة pop(0) في كل قراءة.
class SampleRange:
    def __init__(self):
        self.clear()

    def clear(self):
        self.lo = 101      # أظلم قياس (الخط) — 101 أكبر من أي انعكاس ممكن
        self.hi = -1       # أفتح قياس (الخلفية)
        self.n  = 0        # عدد العينات (للتشخيص)

    def add(self, v):
        if v < self.lo:
            self.lo = v
        if v > self.hi:
            self.hi = v
        self.n += 1

    def ok(self):
        # نحتاج عيّنتين على الأقل وباينًا واضحًا بين الخط والخلفية
        return self.n >= 2 and self.hi >= 0 and self.hi - self.lo >= 25

    def span(self):
        return (self.hi - self.lo) if self.n else 0

refl = SampleRange()

# =========================================================
# 4) دوال مساعدة
# =========================================================
def wait_for_release():
    while hub.buttons.pressed():
        wait(10)

def setup_lines(include_sensors):
    # مقدمة البرنامج الناتج. تُضاف تهيئة الحسّاس (الوحيد) إذا سُجّلت قراءات أو نقاط ذكية،
    # حتى لا يفشل برنامج السباق عند تشغيله بدون حساسات.
    lines = [
        "from pybricks.hubs import PrimeHub",
        "from pybricks.pupdevices import Motor, ColorSensor",
        "from pybricks.parameters import Port, Direction",
        "from pybricks.robotics import DriveBase",
        "from pybricks.tools import wait",
        "",
        "hub = PrimeHub()",
        "left_motor  = Motor(Port.A, Direction.COUNTERCLOCKWISE)",
        "right_motor = Motor(Port.B)",
        "arm_motor   = Motor(Port." + ARM_PORT_LETTER + ")  # محرك الذراع / المهام على المنفذ D",
    ]
    if include_sensors:
        # حساس واحد فقط (المنفذ C) — نفس إعداد نسخة الـ Hub
        lines += [
            "line_sensor = ColorSensor(Port." + LINE_PORT_LETTER + ")  # الحسّاس الوحيد",
        ]
    lines += [
        "robot = DriveBase(left_motor, right_motor, " + str(WHEEL_DIAMETER) + ", " + str(AXLE_TRACK) + ")",
        "robot.use_gyro(True)",
        "# تسارع/تباطؤ محدود = حركة أنعم بلا انتفاضة عند البداية والتوقف",
        "robot.settings(straight_acceleration=" + str(MOVE_ACCEL)
            + ", turn_acceleration=" + str(MOVE_TURN_ACCEL) + ")",
        "robot.reset()",
    ]
    return lines

def estimated_threshold():
    # عتاة الخط = منتصف المسافة بين أفتح قياس (خلفية) وأظلم قياس (خط)
    if refl.ok():
        return (refl.hi + refl.lo) // 2
    return None

def smart_helpers_lines():
    # دوال التصحيح الذكي تُدرج في البرنامج الناتج عند وجود نقاط ذكية.
    #
    # ملاحظة ذاكرة (سبب الخطأ السابق):
    #   كانت هذه الدالة تحتفظ بقالب واحد كبير (~1.5KB) كثابت في الكود،
    #   ثم تستدعي str.replace() ثلاث مرات — وكل استدعاء يخصّص نسخة كاملة
    #   جديدة منه. ذاكرة الهاب في PrimeHub محدودة جدًا، فيفشل الطلب بـ
    #   MemoryError: "allocating 1569 bytes" وينتهي البرنامج كله.
    #   الحل: نبني الأسطر كقوائم نصوص قصيرة تُخصَّص واحدة واحدة، بلا قالب
    #   كبير وبلا replace — ولن يُطلب أي كتلة كبيرة مرة أخرى.
    th = estimated_threshold()
    if th is None:
        th_line = "LINE_THRESHOLD = 30  # عتاة الخط - عايِرها: قِس فوق الخط وفوق الخلفية بزر LEFT"
    else:
        th_line = ("LINE_THRESHOLD = " + str(th) + "  # محسوبة من قياساتك"
                   + " (الخط ≈ " + str(refl.lo) + "، الخلفية ≈ " + str(refl.hi) + ")")
    return [
        "# --- دوال التصحيح الذكي بالحسّاس الواحد ---",
        th_line,
        "",
        "def find_line(direction=1, max_dist=250, speed=80):",
        "    # يتحرك ببطء حتى يكشف الحسّاس خطاً ثم يتوقف (أدقّ من المسار المفتوح)",
        "    robot.reset()",
        "    robot.drive(direction * speed, 0)",
        "    while abs(robot.distance()) < max_dist:",
        "        if line_sensor.reflection() < LINE_THRESHOLD:",
        "            robot.stop()",
        "            return True",
        "        wait(10)",
        "    robot.stop()",
        "    return False",
        "",
        "def align_on_line(speed=" + str(ALIGN_SPEED) + ", max_angle=45):",
        "    # يدور في مكانه حتى يرى الحسّاس الخط (بحث بالدوران)، ثم يتوقف",
        "    # إن كان الحسّاس فوق الخط أصلاً يعود فورًا",
        "    robot.reset()",
        "    robot.drive(0, speed)",
        "    while abs(robot.angle()) < max_angle:",
        "        if line_sensor.reflection() < LINE_THRESHOLD:",
        "            robot.stop()",
        "            return True",
        "        wait(10)",
        "    robot.stop()",
        "    return False",
        "",
        'def follow_line(dist, side="L", speed=90):',
        "    # يتبع حافة الخط بالحسّاس الواحد بتحكم P لمسافة dist مم",
        '    # side = اتجاه التصحيح: "L" نحو اليسار، "R" نحو اليمين',
        "    # المسافة السالبة = متابعة الخط أثناء الرجوع للخلف",
        '    sign = 1 if side == "L" else -1',
        '    spd = speed if dist >= 0 else -speed',
        "    robot.reset()",
        "    while abs(robot.distance()) < abs(dist):",
        "        error = line_sensor.reflection() - LINE_THRESHOLD",
        "        robot.drive(spd, sign * (" + str(FOLLOW_GAIN) + ") * error)",
        "        wait(10)",
        "    robot.stop()",
    ]

def format_seg(seg):
    kind, val = seg
    if kind == "turn":
        return "robot.turn(" + str(val) + ")"
    if kind == "straight":
        return "robot.straight(" + str(val) + ")"
    if kind == "arm":
        return "arm_motor.run_angle(" + str(ARM_SPEED) + ", " + str(val) + ")"
    if kind == "find_line":
        direction, max_dist = val
        return "find_line(" + str(direction) + ", " + str(max_dist) + ")"
    if kind == "align_line":
        return "align_on_line(" + str(val) + ")"
    if kind == "follow_line":
        dist, side = val
        # نطبع الإشارة كما هي: المسافة السالبة = متابعة الخط أثناء الرجوع
        return "follow_line(" + str(dist) + ', "' + side + '")'
    return "# ? " + str(kind) + "=" + str(val)

def merged_moves():
    # يدمج الحركات المتتالية من نفس النوع فقط (turn + turn مثلاً).
    # القطع الذكية تبقى كما هي لأنها معالم مستقلة على المسار.
    merged = []
    for item in actions:
        kind, content = item[0], item[1]
        if kind != "move":
            continue
        for seg in content:
            if seg[0] in ("turn", "straight", "arm") and merged and merged[-1][0] == seg[0]:
                merged[-1] = (seg[0], merged[-1][1] + seg[1])
            else:
                merged.append((seg[0], seg[1]))
    return merged

def print_full_program():
    # زر واحد يطبع برنامج سباق ذكياً كاملاً جاهزاً للنسخ
    # كل ما يُطبع هنا كود صحيح أو تعليق - يمكن نسخ المخرجات كاملة بأمان
    n_cmds = 0
    include_sensors = False
    include_helpers = False
    for item in actions:
        kind, content = item[0], item[1]
        if kind == "move":
            n_cmds += len(content)
            for seg in content:
                if seg[0] in ("find_line", "align_line", "follow_line"):
                    include_helpers = True
                    include_sensors = True
        else:
            include_sensors = True

    # علامتان يلتقط التطبيق ما بينهما ويحوّله إلى ملف .py جاهز للتنزيل.
    # لا تظهران في السجل (التطبيق يخفيهما) ولا تؤثران على الكود.
    print("#@@PROGRAM_BEGIN@@")
    print("")
    print("# " + "=" * 50)
    print("# برنامج السباق الذكي (" + str(n_cmds) + " أمر مسجّل)")
    print("# ناتج آلي من as3_app.py — نزّله من التطبيق كملف .py أو انسخه")
    print("# " + "=" * 50)
    for line in setup_lines(include_sensors):
        print(line)
    if include_helpers:
        for line in smart_helpers_lines():
            print(line)
    print("")
    print("# --- المسار (برنامج واحد؛ أضف run_2() للتكوينات الأخرى")
    print("#     واستدعِها حسب قراءات الحساسات في بداية التشغيل) ---")
    print("def run():")
    printed = False
    for seg in merged_moves():
        if seg[0] in ("turn", "straight", "arm") and seg[1] == 0:
            continue  # قطعان متعاكسان أُلغيَا
        print("    " + format_seg(seg))
        printed = True
    if not printed:
        print("    pass")
    print("")
    print("run()")
    print("# --- نهاية المسار ---")

    if include_sensors:
        print("#")
        print("# --- ملاحظات المعايرة: قراءات الحساسات أثناء التدريب ---")
        for item in actions:
            kind, content = item[0], item[1]
            if kind == "sensor":
                for line in content:
                    print(line)
        if refl.n:
            print("# نطاق الانعكاس: الأقل=" + str(refl.lo) + "، الأعلى=" + str(refl.hi)
                  + " (" + str(refl.n) + " عينة)")
            th = estimated_threshold()
            if th is not None:
                print("# عتاة الخط المقترحة = " + str(th))
    print("#@@PROGRAM_END@@")

def print_sensor(name, s):
    c = s.color()
    r = s.reflection()
    a = s.ambient()
    hsv = s.hsv()
    line = "# " + name + ": color=" + str(c) + ", reflection=" + str(r) + ", ambient=" + str(a) + ", hsv=" + str(hsv)
    print(line)
    return line, r

# =========================================================
# 5) أفعال الأزرار / أوامر التطبيق
#   كل فعل كان داخل حلقة الأزرار أصبح دالة مستقلة، حتى يستطيع
#   زر الروبوت وأمر التطبيق استدعاء نفس الفعل تماماً.
# =========================================================
last_distance  = 0
last_heading   = 0
last_arm_angle = 0

# تسجيل مدخل stdin للاستطلاع دون حظر (non-blocking)
app_input = poll()
app_input.register(stdin)

# ---------------------------------------------------------
# التحكم عن بعد من تطبيق الويب (أزرار الأسهم في app/index.html)
#   الأحرف: w=للأمام s=للخلف a=لف يسارًا d=لف يمينًا
#           u=محرك المنفذ D (+)  j=محرك المنفذ D (-)  x=إيقاف
#   الفكرة: التطبيق يكرر الأمر كل ~250ms ما دام الزر مضغوطًا،
#   والحلقة هنا تنفّذ خطوة صغيرة في كل دورة. إذا توقفت التكرارات
#   (قطع اتصال / نسيان إصبع / خروج من الصفحة) يتباطأ الروبوت
#   ويتوقف تلقائيًا — أي أن أمان الحركة مبنيّ في البروتوكول.
#
# النعومة: بدل القفز من 0 إلى السرعة الكاملة، نقترب من الهدف بمقدار
# محدود في كل دورة (تسارع محدود RC_ACCEL) — فلا تنتفض الحركة ولا
# تتوقف فجأة، ويصبح الإيقاف تباطؤًا قصيرًا (~0.2 ثانية).
# ---------------------------------------------------------
RC_SPEED     = 120  # مم/ث للدفع الأمامي/الخلفي — عدّله حسب روبوتك
RC_TURN      = 90   # درجة/ث للدوران في المكان
                   # (موجب = يمين/مع عقارب الساعة، سالب = يسار — انظر handle_app_command)
RC_ARM_SPEED = 350  # درجة/ث لتحريك محرك المنفذ D عن بعد (ذراع / بوابة)
RC_ARM_MIN_FRAMES = 5  # أدنى نبضة (~150ms) عند النقرة السريعة حتى لا يلغي x أمر u في نفس اللحظة
RC_ACCEL      = 900   # مم/ث²     — تسارع/تباطؤ القيادة (أعلى = أسرع استجابة)
RC_TURN_ACCEL = 1200  # درجة/ث²   — تسارع/تباطؤ الدوران
RC_FRAMES  = 20   # دورات الحلقة (~30-40ms للدورة) قبل الإيقاف التلقائي
                 # ≈ 600-800ms: تحمّل تأخّر البلوتوث البسيط حتى لا يتقطّع
                 # الدفع (التطبيق يعيد الأمر كل 250ms)، ولا يزال يوقف
                 # الروبوت سريعًا إذا انقطع الاتصال فعلًا.

rc_frames  = 0    # العدّاد التنازلي للأمان
rc_target_speed = 0   # الهدف المطلوب من التطبيق
rc_target_turn  = 0
rc_speed   = 0.0  # السرعة الحالية (تتحرك تدريجيًا نحو الهدف)
rc_turn    = 0.0
rc_driving = False

rc_arm_frames  = 0      # عدّاد أمان محرك المنفذ D
rc_arm_min     = 0      # عدّاد أدنى نبضة للنقرة السريعة
rc_arm_target  = 0      # سرعة محرك المنفذ D المطلوبة
rc_arm_speed   = 0      # آخر سرعة فعّالة لمحرك المنفذ D
rc_arm_driving = False

def _approach(cur, target, step):
    # خطوة واحدة نحو الهدف بمقدار أقصاه step
    if cur < target:
        return min(cur + step, target)
    if cur > target:
        return max(cur - step, target)
    return cur

def rc_drive(speed, turn):
    # يبدأ/يجدّد حركة عن بعد؛ تُجدَّد من التطبيق بينما الزر مضغوط
    global rc_frames, rc_target_speed, rc_target_turn, rc_driving
    rc_frames = RC_FRAMES
    rc_target_speed = speed
    rc_target_turn = turn
    if not rc_driving:
        hub.speaker.beep(300, 40)
        rc_driving = True

def rc_arm(speed):
    # يبدأ/يجدّد تحريك محرك المنفذ D عن بعد بينما الزر مضغوط
    global rc_arm_frames, rc_arm_min, rc_arm_target, rc_arm_speed, rc_arm_driving
    m = get_arm()
    if m is None:
        print("# ⚠ لا يوجد محرك موصول على المنفذ D — تأكد من توصيل السلك في المخرج D")
        hub.speaker.beep(250, 200)
        return
    rc_arm_frames = RC_FRAMES
    rc_arm_target = speed
    rc_arm_speed = speed
    if not rc_arm_driving:
        rc_arm_min = RC_ARM_MIN_FRAMES
        hub.speaker.beep(350, 40)
        rc_arm_driving = True
    m.run(int(speed))

def rc_arm_stop():
    # إيقاف وتحرير محرك المنفذ D (coast) ليُحرَّك باليد بحرية
    global rc_arm_frames, rc_arm_min, rc_arm_target, rc_arm_speed, rc_arm_driving
    rc_arm_frames = 0
    rc_arm_min = 0
    rc_arm_target = 0
    rc_arm_speed = 0
    if rc_arm_driving:
        rc_arm_driving = False
        m = get_arm()
        if m is not None:
            m.stop()

def rc_halt():
    # طلب إيقاف ناعم: يُصفّر الهدف ويكمل rc_tick التباطؤ ثم يحرّر المحركات
    global rc_frames, rc_target_speed, rc_target_turn, rc_arm_target, rc_arm_frames
    rc_frames = 0
    rc_target_speed = 0
    rc_target_turn = 0
    rc_arm_target = 0
    if rc_arm_driving:
        if rc_arm_min > 0:
            # نقرة سريعة (وصل u ثم x في نفس الدورة): نترك المحرك يكمل النبضة القصيرة
            rc_arm_frames = rc_arm_min
        else:
            rc_arm_stop()

def rc_release():
    # تحرير المحركات (coast) ليُدفع الروبوت باليد بعده مباشرة
    global rc_driving, rc_speed, rc_turn
    rc_driving = False
    rc_speed = 0
    rc_turn = 0
    left_motor.stop()
    right_motor.stop()
    rc_arm_stop()

def rc_stop():
    # إيقاف فوري بلا تباطؤ — للطوارئ وعند إغلاق البرنامج فقط
    global rc_frames, rc_target_speed, rc_target_turn
    if rc_driving or rc_arm_driving:
        hub.speaker.beep(250, 40)
    rc_frames = 0
    rc_target_speed = 0
    rc_target_turn = 0
    rc_release()

def rc_tick():
    # خطوة واحدة: نقترب من الهدف بتسارع محدود، ثم تباطؤ تلقائي عند انتهاء المهلة
    global rc_frames, rc_speed, rc_turn, rc_target_speed, rc_target_turn, rc_arm_frames, rc_arm_min
    if rc_arm_min > 0:
        rc_arm_min -= 1
    if rc_arm_frames > 0:
        rc_arm_frames -= 1
        if rc_arm_frames == 0:
            rc_arm_stop()
        elif rc_arm_driving:
            m = get_arm()
            if m is not None:
                m.run(int(rc_arm_speed))

    if rc_frames > 0:
        rc_frames -= 1
    elif rc_target_speed or rc_target_turn:
        rc_target_speed = 0
        rc_target_turn = 0

    if not rc_driving:
        return

    rc_speed = _approach(rc_speed, rc_target_speed, RC_ACCEL * 0.03)
    rc_turn  = _approach(rc_turn,  rc_target_turn,  RC_TURN_ACCEL * 0.03)

    # وصلنا للسكون والهدف صفر → حرّر المحركات
    if rc_target_speed == 0 and rc_target_turn == 0 and abs(rc_speed) < 4 and abs(rc_turn) < 6:
        rc_release()
        return

    robot.drive(int(rc_speed), int(rc_turn))

def rc_halt_and_wait():
    # يوقف الدفع بنعومة، وينتظر السكون التام قبل أي أمر تدريب
    rc_halt()
    n = 0
    while (rc_driving or rc_arm_driving) and n < 25:   # حتى ~0.5 ثانية كحد أقصى
        rc_tick()
        wait(20)
        n += 1
    if rc_driving or rc_arm_driving:
        rc_stop()

# ---------------------------------------------------------
# إرسال الكود من التطبيق وتنفيذه على الروبوت
#
#   قبل هذه الميزة كان تشغيل برنامج السباق يحتاج تنزيل ملف .py ثم فتحه
#   في Pybricks Code وتشغيله. الآن يستطيع التطبيق إرسال الكود نفسه إلى
#   الـ Hub: يبدأ بحرف K ثم أسطر قصيرة (سطر لكل أمر) ثم حرف E، ويليه
#   حرف G للتنفيذ — أو يبقى الكود محفوظًا في الـ Hub حتى يُطلب G.
#
#   صيغة السطر الواحد (نفس أوامر برنامج السباق، بلا أقواس):
#     T <زاوية>            → robot.turn
#     S <مسافة>            → robot.straight
#     F <اتجاه> <مسافة>     → find_line
#     A <سرعة>             → align_on_line
#     L <مسافة> <L|R>      → follow_line
#
#   التنفيذ لا يستخدم دوال Pybricks الحاجزة (straight/turn) بل يتقدّم
#   دفعة صغيرة في كل دورة من الحلقة الرئيسية، فيبقى الروبوت يستقبل
#   حرف x (إيقاف) من التطبيق، ويستجيب لأي زر على الهاب في أي لحظة.
# ---------------------------------------------------------
RUN_SPEED        = 220    # مم/ث   — سرعة القطع المستقيم
RUN_TURN_RATE    = 130    # درجة/ث — سرعة الدوران
RUN_ARM_SPEED    = 300    # درجة/ث — سرعة محرك المنفذ D أثناء التنفيذ
RUN_SEARCH_SPEED = 80     # مم/ث   — سرعة البحث عن الخط
RUN_FOLLOW_SPEED = 90     # مم/ث   — سرعة متابعة الخط
RUN_TOL_DIST     = 4      # مم     — سماحية الوصول للمسافة
RUN_TOL_ANG      = 2      # درجة   — سماحية الوصول للزاوية
RUN_TOL_ARM      = 3      # درجة   — سماحية الوصول لزاوية محرك المنفذ D
RUN_ARM_STALL_N  = 15     # دورات ثبات الزاوية قبل اعتبار الذراع وصلت لنهايتها الميكانيكية
RUN_ALIGN_MAX    = 45     # درجة   — أقصى دوران لمحاذاة الخط
RUN_MAX_MS       = 120000 # أمان: أقصى مدة تنفيذ، يُلغى بعدها تلقائيًا
RUN_MAX_LINES    = 90     # أقصى عدد أوامر يُستلم من التطبيق (ذاكرة الـ Hub)
RUN_MAX_LINE_LEN = 24     # أقصى طول سطر مستلم (أطول سطر مدعوم ≈ 12 حرفًا)
HEARTBEAT_MS     = 2500   # نبضة حياة التطبيق: بلا نبضة خلالها يُلغى التنفيذ
CODE_TIMEOUT_MS  = 5000   # مهلة استلام الكود: بلا حرف خلالها نخرج من وضع الاستلام
FRAME_MAX        = 90     # أقصى حمولة في حزمة N (أقل من حدّ خاصية BLE = 100)
TH_MIN           = 5      # أقل عتاة خط مقبولة (H من التطبيق)
TH_MAX           = 95     # أعلى عتاة خط مقبولة

code_mode    = False  # هل نحن في منتصف استلام الكود؟
code_line    = ""     # السطر الجاري تجميعه
code_bad     = False  # هل تجاوز السطر الجاري الحد؟ (يُتجاهل كاملًا)
code_new     = []     # المقاطع المستلمة (تُبنى سطرًا بسطر لتوفير الذاكرة)
code_skipped = 0      # أسطر لم تُفهم أو تجاوزت الحد
code_bulk    = False  # هل الاستلام بحزم N (طريقة التطبيق السريعة)؟
code_single  = False  # أمر إعداد من سطر واحد (H) — يخرج من الاستلام بعد السطر
bulk_hdr     = -1     # -1 = بين الحزم، 0/1 = عدد بايتات الطول المستلمة
bulk_left    = 0      # عدد أحرف الحمولة المتبقية في الحزمة الحالية
PROG_NAME_MAX    = 20     # أقصى طول اسم برنامج محفوظ على الهاب
MAX_PROGRAMS     = 4      # أقصى عدد برامج محفوظة في RAM (ذاكرة الهاب ضيقة)

programs   = []   # [[الاسم, المقاطع], …] — المقاطع نفسها التي تُنفَّذ
single_cmd = ""   # بادئة أمر أحادي السطر: "H" | "W" | "J" | "D"

code_watch   = StopWatch()   # لقياس مهل الاستلام

run_watch    = StopWatch()   # مدة التنفيذ الكلية
beat_watch   = StopWatch()   # آخر نبضة حياة من التطبيق
beat_on      = False         # هل التطبيق يرسل نبضات الآن؟

run_queue  = []      # الأوامر الجاهزة للتنفيذ (مقاطع)
run_active = False   # هل يجري تنفيذ الكود الآن؟
run_index  = 0       # رقم المقطع الجاري
run_phase  = "start" # "start" = تهيئة المقطع، "go" = تنفيذه
run_goal_d = 0       # هدف المسافة للمقطع الحالي
run_goal_h = 0       # هدف الزاوية للمقطع الحالي
run_goal_a = 0       # هدف زاوية محرك المنفذ D للمقطع الحالي
run_arm_last = 0     # آخر زاوية لمحرك D أثناء التنفيذ (لكشف التوقف الميكانيكي)
run_arm_stall = 0    # عدّاد دورات ثبات محرك D
run_base_d = 0       # مسافة البداية للمقطع الحالي
run_base_h = 0       # زاوية البداية للمقطع الحالي
run_th     = 30      # عتاة الخط المستخدمة أثناء التنفيذ
th_pinned  = None    # عتبة وصلت من التطبيق (H) — تُقدَّم على المحسوبة
run_speed  = RUN_FOLLOW_SPEED   # سرعة متابعة الخط أثناء التنفيذ

def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v

def seg_label(seg):
    # نفس شكل السطر في برنامج السباق — ليظهر السجل مفهومًا
    kind = seg[0]
    if kind == "turn":
        return "robot.turn(" + str(seg[1]) + ")"
    if kind == "straight":
        return "robot.straight(" + str(seg[1]) + ")"
    if kind == "arm":
        return "arm_motor.run_angle(" + str(ARM_SPEED) + ", " + str(seg[1]) + ")"
    if kind == "find_line":
        return "find_line(" + str(seg[1]) + ", " + str(seg[2]) + ")"
    if kind == "align_line":
        return "align_on_line(" + str(seg[1]) + ")"
    if kind == "follow_line":
        return "follow_line(" + str(abs(seg[1])) + ', "' + str(seg[2]) + '")'
    return str(kind)

def parse_code_line(line):
    # يحوّل سطرًا قصيرًا من التطبيق إلى مقطع تنفيذ، أو None إن لم يُفهم
    parts = line.split()
    if len(parts) < 2:
        return None
    try:
        k = parts[0]
        if k == "T":
            return ("turn", int(float(parts[1])))
        if k == "S":
            return ("straight", int(float(parts[1])))
        if k == "M":
            return ("arm", int(float(parts[1])))
        if k == "F" and len(parts) >= 3:
            return ("find_line", int(float(parts[1])), int(float(parts[2])))
        if k == "A":
            return ("align_line", int(float(parts[1])))
        if k == "L" and len(parts) >= 3:
            side = "R" if parts[2].upper()[:1] == "R" else "L"
            return ("follow_line", int(float(parts[1])), side)
        if k == "H":
            # عتبة الخط من التطبيق — تُطبَّق فورًا ولا تدخل قائمة التنفيذ
            return ("threshold", int(float(parts[1])))
    except (ValueError, IndexError):
        return None
    return None

def set_threshold(value):
    # H <5..95>: عتاة الخط التي يراها المستخدم في اللوحة — تُرسل قبل G
    # حتى ينفّذ الهاب نفس عتبة الكود المعروض على الشاشة.
    global run_th, th_pinned
    if value < TH_MIN:
        value = TH_MIN
    if value > TH_MAX:
        value = TH_MAX
    run_th = value
    th_pinned = value
    print("# عتاة الخط من التطبيق = " + str(run_th))
    hub.speaker.beep(650, 60)

# ---------------------------------------------------------
# مكتبة برامج على الـ Hub (v9)
#
#   التخزين في RAM: المقاطع نفسها التي يُنفّذها G، بلا نصوص إضافية.
#   الهدف: تشغيل برنامج محفوظ بلا هاتف (J <رقم>)، والتنقّل بين بدائل
#   أثناء التجربة. النسخة الدائمة تبقى في مكتبة التطبيق (localStorage)
#   لأن ذاكرة الـ Hub تُصفَّر عند إعادة التشغيل.
# ---------------------------------------------------------
def store_list():
    # V: قائمة البرامج المحفوظة — بصيغة يفهمها التطبيق
    print("# V " + str(len(programs)))
    i = 0
    for p in programs:
        print("# P " + str(i) + " " + str(len(p[1])) + " " + p[0])
        i += 1
    print("# V end")
    hub.speaker.beep(700, 80)

def store_save(name):
    # W <اسم>: احفظ البرنامج المستلم الآن (run_queue) — يستبدل الاسم نفسه
    if not run_queue:
        print("# ⚠ لا يوجد برنامج لحفظه — أرسل الكود أولًا")
        hub.speaker.beep(250, 250)
        return
    name = name.strip()[:PROG_NAME_MAX]
    if not name:
        name = "برنامج " + str(len(programs) + 1)
    for p in programs:
        if p[0] == name:
            p[1] = run_queue
            print("# ✓ حُدِّث على الهاب: " + name)
            hub.speaker.beep(900, 150)
            return
    if len(programs) >= MAX_PROGRAMS:
        print("# ⚠ امتلأت ذاكرة الـ Hub (" + str(MAX_PROGRAMS) + " برامج) — احذف واحدًا: D <رقم>")
        hub.speaker.beep(250, 250)
        return
    programs.append([name, run_queue])
    print("# ✓ حُفظ على الهاب: " + name + " (" + str(len(programs)) + "/" + str(MAX_PROGRAMS) + ")")
    hub.speaker.beep(900, 150)

def store_run(idx):
    # J <رقم>: شغّل برنامجًا محفوظًا (بلا حاجة إلى إعادة إرسال من الهاتف)
    global run_queue
    if idx < 0 or idx >= len(programs):
        print("# ⚠ لا يوجد برنامج بهذا الرقم — اضغط «تحديث قائمة الـ Hub»")
        hub.speaker.beep(250, 250)
        return
    if run_active:
        run_cancel("تشغيل برنامج محفوظ")
    run_queue = programs[idx][1]
    print("# ▶ برنامج محفوظ: " + programs[idx][0])
    run_start()

def store_del(idx):
    # D <رقم>: احذف برنامجًا محفوظًا
    if idx < 0 or idx >= len(programs):
        print("# ⚠ لا يوجد برنامج بهذا الرقم")
        hub.speaker.beep(250, 250)
        return
    name = programs[idx][0]
    del programs[idx]
    print("# ✗ حُذف من الهاب: " + name + " — المتبقي: " + str(len(programs)))
    hub.speaker.beep(500, 120)

def handle_single(line):
    # أوامر سطر واحد بأرقام (H/W/J/D): تُستلم مثل H ثم تُنفَّذ فورًا
    global single_cmd
    kind = single_cmd
    single_cmd = ""
    parts = line.split()
    arg = parts[1] if len(parts) > 1 else ""
    if kind == "W":
        # الاسم قد يحتوي مسافات: كل ما بعد الحرف الأول
        store_save(line[2:] if len(line) > 2 else "")
        return
    if kind == "H":
        try:
            set_threshold(int(float(arg)))
        except (ValueError, IndexError):
            print("# ⚠ عتاة خط غير صالحة — أُبقيت السابقة")
            hub.speaker.beep(250, 250)
        return
    try:
        idx = int(float(arg))
    except (ValueError, IndexError):
        idx = -1
    if kind == "J":
        store_run(idx)
    elif kind == "D":
        store_del(idx)

def code_add_char(cmd):
    # حرف واحد من نص الكود: يجمعه في السطر الجاري أو ينهيه.
    # تُستخدم في الوضعين: أسطر K…E القديمة، وحزم N الجديدة.
    global code_line, code_bad, code_mode, code_single
    if cmd == "\n":
        code_take_line()
        if code_single:
            code_mode = False
            code_single = False
    elif cmd == "\r":
        pass                        # CR من ويندوز — ليس جزءًا من الأمر
    elif len(code_line) >= RUN_MAX_LINE_LEN:
        # لا نقصّ السطر (قصّ "S 4000" إلى "S 400" ينفّذ أمرًا خاطئًا):
        # نعلّمه فاسدًا ونكمل تجاهله حتى نهاية السطر
        code_bad = True
    else:
        code_line += cmd

def code_take_line():
    # ينهي السطر الجاري ويحوّله فورًا إلى مقطع تنفيذ.
    # لا نحتفظ بنصوص الأسطر كلها (ذاكرة الهاب محدودة) بل بالمقاطع فقط.
    global code_line, code_bad, code_skipped
    line = code_line
    code_line = ""
    if not line:
        code_bad = False
        return
    if code_single:
        # أمر أحادي السطر (H/W/J/D): المسار مختلف — لا مقاطع ولا قائمة تنفيذ
        code_bad = False
        handle_single(line)
        return
    if code_bad:
        # السطر تجاوز الحد: قد يكون مبتورًا (S 4000 → S 400) فلا ننفّذه أبدًا
        code_bad = False
        code_skipped += 1
        return
    if len(code_new) >= RUN_MAX_LINES:
        code_skipped += 1
        return
    seg = parse_code_line(line)
    if seg is None:
        code_skipped += 1
    elif seg[0] == "threshold":
        set_threshold(seg[1])      # H رقم — أمر إعداد لا أمر حركة
    else:
        code_new.append(seg)

def code_receive_start(bulk=False, single=False):
    # K (أسطر) أو B (حزم): بداية استلام كود جديد — يُلغي التنفيذ الجاري.
    # single=True لأمر سطر واحد مثل H (عتبة الخط): يخرج من الاستلام تلقائيًا،
    # وإلا بقي الـ Hub في وضع الاستلام وابتلع أمر G التالي.
    global code_mode, code_bulk, code_single, bulk_hdr, bulk_left
    global code_line, code_bad, code_new, code_skipped
    if run_active:
        run_cancel("استلام كود جديد")
    code_mode = True
    code_bulk = bulk
    code_single = single
    bulk_hdr = -1
    bulk_left = 0
    code_line = ""
    code_bad = False
    code_new = []
    code_skipped = 0
    code_watch.reset()
    if single:
        pass                      # H: بلا رسالة — يظهر سطر العتبة وحده
    elif bulk:
        print("# 📥 استلام الكود من التطبيق (حزم)…")
    else:
        print("# 📥 استلام الكود من التطبيق…")

def code_receive_abort(reason):
    # الخروج الآمن من وضع الاستلام دون لمس الكود السابق في الهاب.
    # بدون هذه المهلة كان فقدُ حرف واحد يُبقي الهاب يبتلع كل الأوامر
    # (حتى x) بلا نهاية.
    global code_mode, code_bulk, code_single, bulk_hdr, bulk_left
    global code_line, code_new, code_bad
    code_mode = False
    code_bulk = False
    code_single = False
    bulk_hdr = -1
    bulk_left = 0
    code_line = ""
    code_new = []
    code_bad = False
    print("# ⚠ أُلغي استلام الكود — " + reason + " (لم يتغيّر الكود السابق)")
    hub.speaker.beep(250, 250)

def code_receive_finish():
    # E: نهاية الاستلام — المقاطع المستلمة تصبح قائمة التنفيذ
    global code_mode, code_bulk, code_single, bulk_hdr, bulk_left
    global code_new, code_skipped, run_queue
    code_take_line()          # آخر سطر إن لم ينتهِ بسطر جديد
    code_mode = False
    code_bulk = False
    code_single = False
    bulk_hdr = -1
    bulk_left = 0
    code_watch.reset()

    n = len(code_new)
    skipped = code_skipped
    if not n:
        print("# ⚠ لم يصل أي أمر صالح — أبقيت الكود السابق كما هو")
        hub.speaker.beep(250, 250)
        code_new = []
        return

    run_queue = code_new
    code_new = []
    msg = "# ✓ استُلم الكود: " + str(n) + " أمرًا"
    if skipped:
        msg += " (تجاهلت " + str(skipped) + " سطرًا)"
    print(msg)
    hub.speaker.beep(900, 120)

def resync_tracking():
    # بعد التشغيل: نُعيد نقطة القياس إلى موضع الروبوت الحالي
    # حتى لا يُسجَّل مسار التنفيذ كأنه حركة يدوية في التسجيل التالي
    global last_distance, last_heading, last_arm_angle
    global watch_d, watch_h, watch_arm, auto_moving, auto_move_mode, auto_idle_ticks
    global seg_samples_total, seg_samples_dark
    last_distance  = robot.distance()
    last_heading   = hub.imu.heading()
    m = get_arm()
    last_arm_angle = m.angle() if m is not None else 0
    watch_d = last_distance
    watch_h = last_heading
    watch_arm = last_arm_angle
    auto_moving = False
    auto_move_mode = None
    auto_idle_ticks = 0
    seg_samples_total = 0
    seg_samples_dark = 0

def _run_end(msg, freq):
    # brake وليس stop: التوقف الآمن يجب أن يكبح المحركات فورًا
    # (stop = coast، أي أن الروبوت قد يتابع مسافة محسوسة بعد الإلغاء).
    global run_active, beat_on
    robot.brake()
    m = get_arm()
    if m is not None:
        m.stop()
    run_active = False
    beat_on = False
    resync_tracking()
    print(msg)
    hub.speaker.beep(freq, 200)

def run_start():
    # G: تنفيذ الكود المستلم الآن
    global run_active, run_index, run_phase, run_th, run_speed, beat_on
    if not run_queue:
        print("# ⚠ لا يوجد كود على الهاب — أرسله من التطبيق أولًا")
        hub.speaker.beep(250, 250)
        return
    if run_active:
        return
    rc_halt_and_wait()          # لا نبدأ والروبوت يتحرك عن بعد
    run_active = True
    run_index = 0
    run_phase = "start"
    # العتبة: ما أرسله التطبيق (H) أولًا، وإلا المحسوبة من العينات، وإلا 30
    th = th_pinned
    if th is None:
        th = estimated_threshold()
    if th is None:
        th = 30
    run_th = th
    run_speed = RUN_FOLLOW_SPEED
    # نبضة الحياة: إن أرسل التطبيق نبضة (p) قبل G نراقبه — ولو انقطع
    # الاتصال أثناء المسار يتوقف الروبوت خلال HEARTBEAT_MS
    beat_watch.reset()
    run_watch.reset()
    print("# ▶ بدء تنفيذ الكود (" + str(len(run_queue)) + " أمر) — عتاة الخط = " + str(run_th))
    print("#   للإيقاف: x من التطبيق أو أي زر على الهاب")
    hub.speaker.beep(1000, 200)

def run_cancel(reason):
    if not run_active:
        robot.brake()
        return
    _run_end("# ⏹ أُلغي تنفيذ الكود — " + reason, 300)

def run_finish():
    _run_end("# ✓ انتهى تنفيذ الكود بنجاح", 800)

def _run_step_straight(dist):
    global run_phase, run_goal_d
    if run_phase == "start":
        run_goal_d = robot.distance() + dist
        run_phase = "go"
        return False
    rem = run_goal_d - robot.distance()
    if abs(rem) <= RUN_TOL_DIST:
        robot.brake()
        return True
    spd = int(_clamp(abs(rem) * 4, 45, RUN_SPEED))
    robot.drive(spd if rem > 0 else -spd, 0)
    return False

def _run_step_turn(angle):
    global run_phase, run_goal_h
    if run_phase == "start":
        # اتجاه الـ IMU مستمر (لا يلتف عند 180) وموجبه مع عقارب الساعة،
        # وهو نفس اتجاه robot.turn — فالمقارنة مباشرة.
        run_goal_h = hub.imu.heading() + angle
        run_phase = "go"
        return False
    err = run_goal_h - hub.imu.heading()
    if abs(err) <= RUN_TOL_ANG:
        robot.brake()
        return True
    rate = int(_clamp(abs(err) * 5, 30, RUN_TURN_RATE))
    robot.drive(0, rate if err > 0 else -rate)
    return False

def _run_step_arm(angle):
    global run_phase, run_goal_a, run_arm_last, run_arm_stall
    m = get_arm()
    if m is None:
        print("# ⚠ لا يوجد محرك موصول على المنفذ D — تم تخطي حركة الذراع")
        return True
    if run_phase == "start":
        run_goal_a = m.angle() + angle
        run_arm_last = m.angle()
        run_arm_stall = 0
        run_phase = "go"
        return False
    cur = m.angle()
    err = run_goal_a - cur
    if abs(err) <= RUN_TOL_ARM:
        m.brake()
        return True
    if abs(cur - run_arm_last) < 1:
        run_arm_stall += 1
        if run_arm_stall >= RUN_ARM_STALL_N:
            # وصلت الذراع لنهايتها الميكانيكية أو أمسكت المكعب: نتوقف بأمان
            m.brake()
            return True
    else:
        run_arm_last = cur
        run_arm_stall = 0
    spd = int(_clamp(abs(err) * 5, 45, RUN_ARM_SPEED))
    m.run(spd if err > 0 else -spd)
    return False

def _run_step_find(direction, max_dist):
    global run_phase, run_base_d
    if run_phase == "start":
        run_base_d = robot.distance()
        run_phase = "go"
        return False
    if line_sensor.reflection() < run_th:
        robot.brake()
        return True
    if abs(robot.distance() - run_base_d) >= max_dist:
        robot.brake()
        return True
    robot.drive(RUN_SEARCH_SPEED if direction >= 0 else -RUN_SEARCH_SPEED, 0)
    return False

def _run_step_align(speed):
    global run_phase, run_base_h
    if run_phase == "start":
        run_base_h = hub.imu.heading()
        run_phase = "go"
        return False
    if line_sensor.reflection() < run_th:
        robot.brake()
        return True
    if abs(hub.imu.heading() - run_base_h) >= RUN_ALIGN_MAX:
        robot.brake()
        return True
    robot.drive(0, speed)
    return False

def _run_step_follow(dist, side):
    global run_phase, run_base_d
    if run_phase == "start":
        run_base_d = robot.distance()
        run_phase = "go"
        return False
    if abs(robot.distance() - run_base_d) >= abs(dist):
        robot.brake()
        return True
    sign = 1 if side == "L" else -1
    # المسافة السالبة = متابعة الخط أثناء الرجوع للخلف
    spd = run_speed if dist >= 0 else -run_speed
    robot.drive(spd, int(sign * FOLLOW_GAIN * (line_sensor.reflection() - run_th)))
    return False

def run_tick():
    # خطوة واحدة من تنفيذ الكود — تُنادى من الحلقة الرئيسية كل دورة
    global run_active, run_index, run_phase
    if not run_active:
        return
    if run_watch.time() > RUN_MAX_MS:
        run_cancel("تجاوز مدة الأمان")
        return
    # نبضة الحياة: التطبيق يرسل p كل ثانية. إن توقفت (خروج من المدى،
    # إغلاق التبويب، تعليق الجوال) نوقف الروبوت بدل إكمال المسار وحده.
    if beat_on and beat_watch.time() > HEARTBEAT_MS:
        run_cancel("انقطاع الاتصال بالتطبيق")
        return
    if run_index >= len(run_queue):
        run_finish()
        return

    seg = run_queue[run_index]
    if run_phase == "start":
        print("# " + str(run_index + 1) + "/" + str(len(run_queue)) + "  " + seg_label(seg))

    kind = seg[0]
    if kind == "straight":
        done = _run_step_straight(seg[1])
    elif kind == "turn":
        done = _run_step_turn(seg[1])
    elif kind == "arm":
        done = _run_step_arm(seg[1])
    elif kind == "find_line":
        done = _run_step_find(seg[1], seg[2])
    elif kind == "align_line":
        done = _run_step_align(seg[1])
    elif kind == "follow_line":
        done = _run_step_follow(seg[1], seg[2])
    else:
        done = True

    if done:
        run_index += 1
        run_phase = "start"

# ---------------------------------------------------------
# قراءة الحساسات والتسجيل التلقائي الذكي للمسار بدون أزرار (WRO 2026)
#   - تُجمع العينات دائمًا في الخلفية (تُحسّن حساب عتبة الخط).
#   - ويُبثّ سطر قياس في السجل أثناء الحركة فقط (بالأسهم أو باليد).
#   - عند تفعيل AUTO_RECORD: يكتشف التوقف اللحظي (~0.5 ثانية) أو تغيّر نوع
#     الحركة (دوران ← مستقيم ← ذراع) فيسجّل الخطوة تلقائيًا، مع تثبيت
#     الزوايا القريبة من 90° واكتشاف الخط الأسود (find_line / follow_line)
#     وتحديث كود السباق في التطبيق مباشرةً.
# ---------------------------------------------------------
AUTO_SAMPLE_EVERY  = 3     # كل 3 دورات ≈ 100ms
AUTO_STREAM        = True  # بثّ القراءات في السجل أثناء الحركة
MOVE_EPS_DIST      = 8     # مم — للبثّ في السجل
MOVE_EPS_ANG       = 3     # درجة — للبثّ في السجل
MOVE_EPS_ARM       = 5     # درجات محرك المنفذ D

# عتبات السكون الدقيق والتسجيل التلقائي (تعمل حتى مع التحريك اليدوي الهادئ والبطيء)
STILL_EPS_DIST     = 2     # مم لكل 100ms — أقل من ذلك يُعدّ الروبوت ساكنًا تمامًا
STILL_EPS_ANG      = 1     # درجة لكل 100ms
STILL_EPS_ARM      = 2     # درجتان لكل 100ms على محرك الذراع D
AUTO_MIN_DIST      = 15    # مم — أقل مسافة تُسجَّل تلقائيًا (يتجاهل اهتزاز اللمس)
AUTO_MIN_ANG       = 5     # درجات — أقل زاوية دوران تُسجَّل تلقائيًا
AUTO_MIN_ARM       = 8     # درجات — أقل حركة ذراع تُسجَّل تلقائيًا
TURN_PIVOT_ROLL_MAX = 40   # مم — تجاهل دحرجة العجلات العرضية (< 40مم) أثناء تدوير الروبوت باليد (≥ 25°)

AUTO_RECORD        = True  # التسجيل التلقائي الذكي للمسار بدون ضغط أزرار (m تشغيل / n إيقاف)
SNAP_90            = True  # تثبيت الزوايا القائمة 90°/180° لبساط WRO 2026 (g تشغيل / h إيقاف)
AUTO_LINE_DETECT   = True  # اكتشاف الخط الأسود تلقائيًا find_line / follow_line (i تشغيل / o إيقاف)
AUTO_PRINT_PROG    = False # لا نطبع 80 سطرًا بعد كل خطوة لمنع تجمّد البلوتوث؛ التطبيق يحدّث الكود لحظيًا
AUTO_SETTLE_TICKS  = 6     # 6 قراءات سكون متتالية (~0.6 ثانية) = حفظ النقطة تلقائيًا
SNAP_90_TOL        = 12    # هامش تثبيت الزاوية القائمة (±12 درجة حول مضاعفات 90°)
STRAIGHT_DRIFT_MAX = 7     # تجاهل انحراف اليد العرضي (< 7 درجات) أثناء الدفع المستقيم
FOLLOW_DARK_RATIO  = 0.55  # نسبة القراءات الداكنة لاعتبار المشي الطويل (≥120مم) تتبع خط follow_line

auto_tick = 0
watch_d = 0
watch_h = 0
watch_arm = 0
auto_moving = False
auto_move_mode = None
auto_idle_ticks = 0
seg_samples_total = 0
seg_samples_dark = 0
seg_start_dark = False

def sample_sensors(keep):
    # يقرأ الحسّاس الوحيد، ويضيف العينة لنطاق المعايرة إذا طُلب.
    # keep=False عند السكون: العيّنة الساكنة (ظلّ يد أو روبوت مرفوع) تُفسد العتبة.
    v = line_sensor.reflection()
    if keep:
        refl.add(v)
    return v

def snap_turn_angle(diff_head):
    # تثبيت الزوايا القريبة من مضاعفات 90° لبساط WRO 2026 (كل تقاطعاته 90°)
    deg = int(round(diff_head))
    if not SNAP_90:
        return deg, False
    nearest_90 = int(round(diff_head / 90.0)) * 90
    if nearest_90 != 0 and abs(diff_head - nearest_90) <= SNAP_90_TOL:
        return nearest_90, (deg != nearest_90)
    return deg, False

def _active_line_threshold():
    th = th_pinned
    if th is None:
        th = estimated_threshold()
    if th is None:
        th = 22
    return th

def do_auto_record_segment(curr_refl=None, mode_switch=False):
    global last_distance, last_heading, last_arm_angle
    global seg_samples_total, seg_samples_dark, seg_start_dark
    curr_distance = robot.distance()
    curr_heading  = hub.imu.heading()
    m = get_arm()
    curr_arm      = m.angle() if m is not None else last_arm_angle

    diff_dist = curr_distance - last_distance
    diff_head = curr_heading - last_heading
    diff_arm  = curr_arm - last_arm_angle

    # 1) تجاهل انحراف اليد العرضي (< STRAIGHT_DRIFT_MAX) أثناء الدفع المستقيم
    ignore_drift = (SNAP_90 and abs(diff_dist) >= 45 and abs(diff_head) < STRAIGHT_DRIFT_MAX)
    # 2) تجاهل دحرجة العجلات العرضية (< TURN_PIVOT_ROLL_MAX) أثناء لف الروبوت باليد في مكانه
    ignore_pivot_roll = (abs(diff_head) >= 25 and abs(diff_dist) < TURN_PIVOT_ROLL_MAX)

    segs = []
    did_turn = False
    did_straight = False
    did_line = False
    did_arm = False
    snapped_turn = None

    if not ignore_drift and abs(diff_head) >= AUTO_MIN_ANG:
        turn_deg, was_snapped = snap_turn_angle(diff_head)
        if was_snapped:
            print("# 📐 تثبيت تلقائي للزاوية القائمة: " + str(int(round(diff_head))) + "° ← " + str(turn_deg) + "°")
        segs.append(("turn", turn_deg))
        snapped_turn = turn_deg
        did_turn = True

    th = _active_line_threshold()

    if not ignore_pivot_roll and abs(diff_dist) >= AUTO_MIN_DIST:
        dist_int = int(round(diff_dist))
        if (AUTO_LINE_DETECT and abs(dist_int) >= 120 and seg_samples_total >= 3
                and (seg_samples_dark / seg_samples_total) >= FOLLOW_DARK_RATIO):
            print("# 〰️ اكتشاف تلقائي لتتبع الخط الأسود ← follow_line")
            segs.append(("follow_line", (dist_int, FOLLOW_SIDE)))
            did_line = True
        elif (AUTO_LINE_DETECT and curr_refl is not None and curr_refl <= th
                and not seg_start_dark and not mode_switch):
            direction = 1 if dist_int >= 0 else -1
            max_dist = max(abs(dist_int) + SEARCH_MARGIN, MIN_SEARCH)
            print("# 🎯 اكتشاف تلقائي لخط التوقف الأسود ← find_line")
            segs.append(("find_line", (direction, max_dist)))
            did_line = True
        else:
            segs.append(("straight", dist_int))
            did_straight = True

    if abs(diff_arm) >= AUTO_MIN_ARM:
        segs.append(("arm", int(round(diff_arm))))
        did_arm = True

    seg_samples_total = 0
    seg_samples_dark = 0
    seg_start_dark = (curr_refl is not None and curr_refl <= th)

    if not segs:
        return False

    if push_action("move", segs, last_distance, last_heading, last_arm_angle):
        print("# ✨ تسجيل تلقائي:")
        for seg in segs:
            print(format_seg(seg))
        last_distance = curr_distance
        if snapped_turn is not None:
            # نربط الزاوية المرجعية بالزاوية المثبّتة (90°/180°) لمنع تراكم خطأ اليد
            if abs(curr_heading - (last_heading + snapped_turn)) <= SNAP_90_TOL:
                last_heading = last_heading + snapped_turn
            else:
                last_heading = curr_heading
        elif not ignore_drift:
            last_heading = curr_heading
        last_arm_angle = curr_arm

        if did_arm:
            hub.speaker.beep(700, 50)
            hub.speaker.beep(950, 60)
        elif did_line:
            hub.speaker.beep(1050, 65)
        elif did_turn:
            hub.speaker.beep(850, 55)
        elif did_straight:
            hub.speaker.beep(650, 55)

        if AUTO_PRINT_PROG and not mode_switch:
            do_print_program()
        return True
    return False

def auto_read_tick():
    # تُنادى كل دورة من الحلقة الرئيسية؛ تقرأ كل ~100ms
    global auto_tick, watch_d, watch_h, watch_arm
    global auto_moving, auto_move_mode, auto_idle_ticks
    global seg_samples_total, seg_samples_dark, seg_start_dark
    auto_tick += 1
    if auto_tick < AUTO_SAMPLE_EVERY:
        return
    auto_tick = 0

    d = robot.distance()
    h = hub.imu.heading()
    m = get_arm()
    a = m.angle() if m is not None else last_arm_angle

    step_d = d - watch_d
    step_h = h - watch_h
    step_a = a - watch_arm

    hand_moved = (abs(step_d) >= MOVE_EPS_DIST
                  or abs(step_h) >= MOVE_EPS_ANG
                  or abs(step_a) >= MOVE_EPS_ARM)
    watch_d = d
    watch_h = h
    watch_arm = a

    v = sample_sensors(hand_moved or rc_driving)

    # أثناء تنفيذ الكود لا نبثّ سطر قياس لكل خطوة (لئلا يمتلئ السجل)،
    # فالتطبيق يعرض تقدّم التنفيذ سطرًا لكل مقطع.
    if AUTO_STREAM and not run_active and (rc_driving or rc_arm_driving or hand_moved):
        # سطر مضغوط: d=المسافة h=الاتجاه C=انعكاس الحسّاس الوحيد
        print("# T d=" + str(int(d)) + " h=" + str(int(h)) + " C=" + str(v))

    # --- آلة التسجيل التلقائي الذكي للمسار بدون أزرار ---
    if not AUTO_RECORD or run_active or code_mode:
        return

    th = _active_line_threshold()

    # هل ابتعد الروبوت أو الذراع عن آخر نقطة مسجّلة؟ (يكتشف حتى التحريك اليدوي الهادئ والبطيء)
    total_d = d - last_distance
    total_h = h - last_heading
    total_a = a - last_arm_angle
    displaced = (abs(total_d) >= AUTO_MIN_DIST
                 or abs(total_h) >= AUTO_MIN_ANG
                 or abs(total_a) >= AUTO_MIN_ARM)

    # هل الروبوت والذراع ساكنان تمامًا في هذه اللحظة؟
    is_still_now = (abs(step_d) <= STILL_EPS_DIST
                    and abs(step_h) <= STILL_EPS_ANG
                    and abs(step_a) <= STILL_EPS_ARM
                    and not rc_driving
                    and not rc_arm_driving)

    if not is_still_now or (displaced and not auto_moving):
        if not auto_moving:
            auto_moving = True
            seg_start_dark = (v <= th)
            seg_samples_total = 0
            seg_samples_dark = 0
        if not is_still_now:
            auto_idle_ticks = 0
            if abs(step_d) > STILL_EPS_DIST or rc_driving:
                seg_samples_total += 1
                if v <= th:
                    seg_samples_dark += 1
            return

    if auto_moving and is_still_now:
        auto_idle_ticks += 1
        if auto_idle_ticks >= AUTO_SETTLE_TICKS:
            do_auto_record_segment(v, mode_switch=False)
            auto_moving = False
            auto_move_mode = None
            auto_idle_ticks = 0

MAX_ACTIONS = 60   # أقصى عدد تسجيلات (ذاكرة الـ Hub محدودة)

def push_action(kind, content, prev_dist=None, prev_head=None, prev_arm=None):
    # يضيف تسجيلًا مع احترام الحد الأقصى؛ يعيد False إن رُفض.
    # عند الرفض لا نحرّك نقطة القياس: الحركة تبقى «غير مسجَّلة» فيلتقطها
    # التسجيل التالي بدل أن تُفقد بصمت.
    if len(actions) >= MAX_ACTIONS:
        print("# ⚠ بلغ الحد الأقصى للتسجيلات (" + str(MAX_ACTIONS)
              + ") — احذف بعضها بـ U ثم أعد المحاولة")
        hub.speaker.beep(250, 250)
        return False
    actions.append((kind, content, prev_dist, prev_head, prev_arm))
    return True

def do_undo():
    global last_distance, last_heading, last_arm_angle
    # تراجع: يحذف كل ما أضافته آخر ضغطة دفعة واحدة ويعيد المرجع السابق
    if actions:
        item = actions.pop()
        kind, content, prev_dist, prev_head = item[0], item[1], item[2], item[3]
        prev_arm = item[4] if len(item) > 4 and item[4] is not None else last_arm_angle
        if kind == "move":
            for seg in content:
                print("# حذف: " + format_seg(seg))
            # إرجاع نقطة القياس حتى يمكن إعادة تسجيل نفس الحركة
            last_distance  = prev_dist
            last_heading   = prev_head
            last_arm_angle = prev_arm
        else:
            print("# حذف قراءات الحساسات الأخيرة")
    else:
        print("# لا يوجد ما يُحذف")
    hub.speaker.beep(400, 150)

def do_clear_path():
    # تصفير المسار بالكامل والبدء من موضع الروبوت الحالي (مربع START)
    global AUTO_RECORD
    actions.clear()
    resync_tracking()
    AUTO_RECORD = True
    hub.light.on(Color.GREEN)
    print("# 🗑️ تم مسح المسار وتصفير نقطة القياس — جاهز للتدريب من جديد")
    hub.speaker.beep(600, 80)
    hub.speaker.beep(400, 100)
    if AUTO_PRINT_PROG:
        do_print_program()

def do_find_line_point():
    global last_distance, last_heading
    # نقطة خط ذكية: تستبدل الحركة منذ آخر تسجيل ببحث دقيق عن الخط.
    #   وإذا كان التسجيل التلقائي قد سجّل الحركة للتو كمشي مستقيم، نحوّل آخر
    #   مقطع مستقيم مسجّل إلى find_line مباشرةً.
    curr_distance = robot.distance()
    curr_heading = hub.imu.heading()
    diff_dist = curr_distance - last_distance
    diff_head = curr_heading - last_heading

    refl.add(line_sensor.reflection())

    if abs(diff_dist) < MIN_DIST and abs(diff_head) < MIN_ANG and actions:
        last_item = actions[-1]
        if last_item[0] == "move" and last_item[1]:
            last_seg = last_item[1][-1]
            if last_seg[0] in ("straight", "follow_line"):
                prev_d = last_seg[1] if last_seg[0] == "straight" else last_seg[1][0]
                direction = 1 if prev_d >= 0 else -1
                max_dist = max(abs(int(round(prev_d))) + SEARCH_MARGIN, MIN_SEARCH)
                new_seg = ("find_line", (direction, max_dist))
                print("# حذف: " + format_seg(last_seg))
                last_item[1][-1] = new_seg
                print(format_seg(new_seg))
                hub.speaker.beep(500, 80)
                if AUTO_PRINT_PROG:
                    do_print_program()
                return

    segs = []
    if abs(diff_head) >= MIN_ANG:
        segs.append(("turn", int(round(diff_head))))

    direction = 1 if diff_dist >= 0 else -1
    max_dist = max(int(round(abs(diff_dist))) + SEARCH_MARGIN, MIN_SEARCH)
    segs.append(("find_line", (direction, max_dist)))

    if push_action("move", segs, last_distance, last_heading, last_arm_angle):
        for seg in segs:
            print(format_seg(seg))
        last_distance = curr_distance
        last_heading = curr_heading
        hub.speaker.beep(500, 80)

def do_follow_line_seg():
    global last_distance, last_heading
    # مقطع متابعة خط: يتبع الحافة بالمسافة المجرَّبة منذ آخر تسجيل
    curr_distance = robot.distance()
    curr_heading = hub.imu.heading()
    diff_dist = curr_distance - last_distance
    diff_head = curr_heading - last_heading

    refl.add(line_sensor.reflection())

    if abs(diff_dist) < MIN_DIST and abs(diff_head) < MIN_ANG and actions:
        last_item = actions[-1]
        if last_item[0] == "move" and last_item[1]:
            last_seg = last_item[1][-1]
            if last_seg[0] == "straight":
                prev_d = int(round(last_seg[1]))
                new_seg = ("follow_line", (prev_d, FOLLOW_SIDE))
                print("# حذف: " + format_seg(last_seg))
                last_item[1][-1] = new_seg
                print(format_seg(new_seg))
                hub.speaker.beep(550, 80)
                if AUTO_PRINT_PROG:
                    do_print_program()
                return

    segs = []
    if abs(diff_head) >= MIN_ANG:
        segs.append(("turn", int(round(diff_head))))

    if abs(diff_dist) >= MIN_DIST:
        # الجانب من الثابت FOLLOW_SIDE (لا مقارنة حساسين بعد الآن)
        # نحفظ الإشارة: الدفع للخلف يبقى متابعة خط بالخلف
        segs.append(("follow_line", (int(round(diff_dist)), FOLLOW_SIDE)))

    if segs:
        if push_action("move", segs, last_distance, last_heading, last_arm_angle):
            for seg in segs:
                print(format_seg(seg))
            last_distance = curr_distance
            last_heading = curr_heading
            hub.speaker.beep(550, 80)
    else:
        print("# حركة أصغر من العتبة - تم تجاهلها")

def do_record_move():
    global last_distance, last_heading, last_arm_angle
    curr_distance = robot.distance()
    curr_heading  = hub.imu.heading()
    m = get_arm()
    curr_arm      = m.angle() if m is not None else last_arm_angle

    diff_dist = curr_distance - last_distance
    diff_head = curr_heading - last_heading  # درجات (موجب = مع عقارب الساعة)
    diff_arm  = curr_arm - last_arm_angle    # درجات محرك المنفذ D

    did_straight = False
    did_turn = False
    did_arm = False
    segs = []

    # الدوران أولاً ثم المستقيم ثم محرك الذراع D
    if abs(diff_head) >= MIN_ANG:
        segs.append(("turn", int(round(diff_head))))
        did_turn = True
    if abs(diff_dist) >= MIN_DIST:
        segs.append(("straight", int(round(diff_dist))))
        did_straight = True
    if abs(diff_arm) >= MIN_ARM_ANG:
        segs.append(("arm", int(round(diff_arm))))
        did_arm = True

    if segs:
        # نحفظ المرجع السابق داخل العنصر حتى يستعيده التراجع
        if push_action("move", segs, last_distance, last_heading, last_arm_angle):
            for seg in segs:
                print(format_seg(seg))
            last_distance  = curr_distance
            last_heading   = curr_heading
            last_arm_angle = curr_arm
            if did_turn:
                hub.speaker.beep(800, 80)
            if did_straight:
                hub.speaker.beep(600, 80)
            if did_arm:
                hub.speaker.beep(700, 80)
    else:
        print("# حركة أصغر من العتبة - تم تجاهلها")

def do_read_sensors():
    line, ref = print_sensor("LINE sensor (Port." + LINE_PORT_LETTER + ")", line_sensor)
    refl.add(ref)
    if push_action("sensor", [line]):
        hub.speaker.beep(750, 80)

def do_print_program():
    try:
        print_full_program()
    except MemoryError:
        # فشل الذاكرة أثناء الطباعة: نغلق علامات الالتقاط حتى لا تبقى
        # لوحة التطبيق معلّقة على نص ناقص، ونشرح ما حدث بدل انتهاء البرنامج
        print("#@@PROGRAM_END@@")
        print("# ⚠ نفد ذاكرة الهاب: لم يكتمل طباعة البرنامج")
        print("#   احذف بعض التسجيلات (U) ثم اضغط طباعة مرة أخرى (C)")
        hub.speaker.beep(250, 250)
        return
    hub.speaker.beep(900, 150)

def handle_app_command(cmd):
    # حرف واحد من التطبيق = نفس ضغطة الزر المقابلة على الروبوت
    global AUTO_STREAM, AUTO_RECORD, SNAP_90, AUTO_LINE_DETECT
    global code_mode, code_line, code_bad, beat_on

    # --- استلام الكود من التطبيق ---
    if code_mode:
        code_watch.reset()
        if code_bulk:
            # وضع الحزم: N + بايتان طول + حمولة. الأسطر قد تنقسم بين حزمتين.
            global bulk_hdr, bulk_left
            if bulk_hdr >= 0:
                # نجمع طول الحمولة (little-endian) قبل بياناتها
                if bulk_hdr == 0:
                    bulk_left = ord(cmd)
                else:
                    bulk_left += 256 * ord(cmd)
                bulk_hdr += 1
                if bulk_hdr > 1:
                    bulk_hdr = -1
                    if bulk_left > FRAME_MAX:
                        code_receive_abort("حزمة أكبر من الحد")
                return
            if bulk_left > 0:
                code_add_char(cmd)
                bulk_left -= 1
                return
            if cmd == "N":
                bulk_hdr = 0          # ابدأ حزمة جديدة
            elif cmd == "E":
                code_receive_finish()
            # أي شيء آخر بين الحزم يُتجاهل
            return

        # وضع الأسطر القديم: K … نص … E
        if cmd == "E":
            # نهاية الإرسال دائمًا — حتى لو بقي نص في السطر (فشل حرف سابق)
            code_receive_finish()
        else:
            code_add_char(cmd)
        return

    # --- نبضة حياة التنفيذ: p تشغيل المراقب، q إيقافه ---
    if cmd == "p":
        beat_on = True
        beat_watch.reset()
        return
    if cmd == "q":
        beat_on = False
        return

    if cmd == "K":
        code_receive_start(False)
        return
    if cmd == "B":
        code_receive_start(True)
        return
    if cmd == "E":
        code_receive_finish()
        return
    if cmd == "G":
        run_start()
        return
    if cmd == "?":
        # نبضة تشخيص: تُخبر التطبيق أن برنامج التدريب يعمل ويقرأ الأوامر.
        # بدونها لا يستطيع التطبيق التمييز بين «أمر لم يُنفَّذ» و«لا أحد يسمع».
        print("# ✓ HUB_ALIVE v" + HUB_VERSION + " " + str(len(run_queue)) + " " + str(gc.mem_free()))
        hub.speaker.beep(1200, 40)
        return
    if cmd == "V":
        # قائمة البرامج المحفوظة على الـ Hub بلا وسيط
        store_list()
        return
    if cmd in ("H", "W", "J", "D"):
        # أمر بسطر واحد: الحرف ثم الوسيط ثم سطر جديد — يعود الـ Hub جاهزًا بعده
        global single_cmd
        code_receive_start(False, True)
        code_line = cmd + " "
        single_cmd = cmd
        return

    # --- إيقاف: تنفيذ كود جارٍ أو تحرير المحركات ---
    if cmd == "x":
        if run_active:
            run_cancel("من التطبيق")
        else:
            rc_halt()                    # تباطؤ ناعم ثم تحرير المحركات
        return

    # أي أمر آخر أثناء تنفيذ الكود = إيقافه فورًا (أمان)
    if run_active and cmd != "y" and cmd != "z":
        run_cancel("أمر جديد من التطبيق")

    # --- قراءة الحساسات التلقائية: y تشغيل / z إيقاف ---
    if cmd == "y":
        AUTO_STREAM = True
        print("# القراءة التلقائية للحساسات: مفعّلة")
        hub.speaker.beep(700, 60)
        return
    if cmd == "z":
        AUTO_STREAM = False
        print("# القراءة التلقائية للحساسات: متوقفة")
        hub.speaker.beep(500, 60)
        return

    # --- التسجيل التلقائي الذكي بدون أزرار: m تشغيل / n إيقاف ---
    if cmd == "m":
        AUTO_RECORD = True
        resync_tracking()
        hub.light.on(Color.GREEN)
        print("# 🤖 التسجيل التلقائي الذكي للمسار: مفعّل")
        hub.speaker.beep(780, 60)
        return
    if cmd == "n":
        if auto_moving:
            do_auto_record_segment(line_sensor.reflection(), mode_switch=False)
        AUTO_RECORD = False
        resync_tracking()
        hub.light.on(Color.BLUE)
        print("# 🤖 التسجيل التلقائي الذكي للمسار: متوقف")
        hub.speaker.beep(520, 60)
        return

    # --- تثبيت الزوايا القائمة 90° لبساط WRO 2026: g تشغيل / h إيقاف ---
    if cmd == "g":
        SNAP_90 = True
        print("# 📐 تثبيت الزوايا القائمة 90°: مفعّل")
        hub.speaker.beep(820, 60)
        return
    if cmd == "h":
        SNAP_90 = False
        print("# 📐 تثبيت الزوايا القائمة 90°: متوقف")
        hub.speaker.beep(540, 60)
        return

    # --- الاكتشاف التلقائي للخط الأسود (find_line / follow_line): i تشغيل / o إيقاف ---
    if cmd == "i":
        AUTO_LINE_DETECT = True
        print("# 🎯 الاكتشاف التلقائي للخط الأسود: مفعّل")
        hub.speaker.beep(860, 60)
        return
    if cmd == "o":
        AUTO_LINE_DETECT = False
        print("# 🎯 الاكتشاف التلقائي للخط الأسود: متوقف")
        hub.speaker.beep(560, 60)
        return

    # --- مسح المسار وتصفير نقطة البداية (مربع START): 0 ---
    if cmd == "0":
        if rc_driving or rc_arm_driving:
            rc_halt_and_wait()
        do_clear_path()
        return

    # --- التحكم عن بعد بالمحركات (الأسهم في التطبيق + محرك D) ---
    #   ملاحظة: القيمة الموجبة لمعدّل الدوران تعني يمينًا (مع عقارب الساعة).
    if cmd == "w":                       # للأمام
        rc_drive(RC_SPEED, 0)
        return
    if cmd == "s":                       # للخلف
        rc_drive(-RC_SPEED, 0)
        return
    if cmd == "a":                       # لف يسارًا  (عكس عقارب الساعة)
        rc_drive(0, -RC_TURN)
        return
    if cmd == "d":                       # لف يمينًا  (مع عقارب الساعة)
        rc_drive(0, RC_TURN)
        return
    if cmd == "u":                       # محرك المنفذ D (+) رفع / فتح
        rc_arm(RC_ARM_SPEED)
        return
    if cmd == "j":                       # محرك المنفذ D (-) خفض / إغلاق
        rc_arm(-RC_ARM_SPEED)
        return

    # --- أي أمر تدريب: أوقف الدفع عن بعد بنعومة حتى لا تتداخل الحركتان ---
    if rc_driving or rc_arm_driving:
        rc_halt_and_wait()

    if cmd == "R":
        do_record_move()
    elif cmd == "L":
        do_read_sensors()
    elif cmd == "C":
        do_print_program()
    elif cmd == "F":
        do_find_line_point()
    elif cmd == "T":
        do_follow_line_seg()
    elif cmd == "U":
        do_undo()
    # أي حرف آخر (مسافات، أسطر جديدة…) يُتجاهل

# =========================================================
# 6) البرنامج الرئيسي: توليد كود ذكي من التدريب
# =========================================================
for line in setup_lines(False):
    print(line)

left_motor.stop()   # coast: تُترك المحركات حرة ليُدفع الروبوت باليد
right_motor.stop()
if get_arm() is not None:
    arm_motor.stop()    # coast: يُترك محرك المنفذ D حراً لتحريك الذراع باليد
    arm_motor.reset_angle(0)

robot.reset()  # تصفير عدادات المسافة والزاوية (والجيرو)

last_distance  = robot.distance()
last_heading   = hub.imu.heading()
last_arm_angle = arm_motor.angle() if arm_motor is not None else 0

hub.light.on(Color.BLUE)
print("")
print("# HUB_VERSION " + HUB_VERSION)
print("# برامج محفوظة على الهاب: " + str(len(programs)) + "/" + str(MAX_PROGRAMS) + " (RAM)")
print("# ذاكرة حرة: " + str(gc.mem_free()) + " بايت")
print("# جاهز: حرّك الروبوت بيدك أو من تطبيق الويب، ثم اضغط للتسجيل")
print("# التطبيق: R تسجيل حركة | L قراءة حساسات | C طباعة البرنامج")
print("#          F نقطة خط ذكية | T متابعة خط | U تراجع")
print("#          أزرار الأسهم: w/s/d/a للتحريك + u/j لمحرك D، x = إيقاف")
print("#          القراءة التلقائية: y تشغيل | z إيقاف (سطور # T أثناء الحركة)")
print("#          إرسال الكود من التطبيق: K استلام ← أسطر ← E انتهى ← G تنفيذ")
print("#          H ثم الرقم = عتاة الخط للتنفيذ | p/q نبضة الحياة | x إيقاف")
print("#          و x أثناء التنفيذ = إيقافه فورًا")
print("# أزرار الروبوت ما زالت تعمل:")
print("# - RIGHT       : تسجيل حركة (دوران ثم مستقيم + محرك D)")
print("# - LEFT        : تسجيل قراءة الحسّاس (لحساب عتاة الخط)")
print("# - CENTER+LEFT : نقطة خط ذكية find_line (+ محاذاة) بدل آخر مستقيم")
print("# - CENTER+RIGHT: مقطع متابعة خط follow_line بآخر مسافة")
print("# - LEFT+RIGHT  : حذف آخر تسجيل (مع إرجاع نقطة القياس)")
print("# - CENTER      : طباعة برنامج السباق الذكي الكامل")
print("# APP_READY")

try:
    while True:
        # 0) مهل الاستلام الآمنة: إن انقطع الإرسال بعد K (أو تعطّل حرف)
        #    نخرج من وضع الاستلام تلقائيًا بدل ابتلاع كل الأوامر بلا نهاية
        if code_mode and code_watch.time() > CODE_TIMEOUT_MS:
            code_receive_abort("مهلة الاستلام انتهت (5 ثوانٍ بلا بيانات)")

        # 1) أوامر التطبيق الواصلة عبر البلوتوث (stdin) - دون حظر الحلقة
        while app_input.poll(0):
            ch = stdin.read(1)
            if not ch:
                break
            try:
                handle_app_command(ch)
            except MemoryError:
                # أي أمر آخر نفد فيه الذاكرة: نكمل الحلقة بدل انتهائها
                print("# ⚠ نفد الذاكرة — تجاهل الأمر واستمر")
                hub.speaker.beep(250, 250)

        # 2) أزرار الروبوت الفعلية (نفس أولوية الفحص السابقة)
        #    أي زر يوقف الدفع عن بعد أو تنفيذ الكود أولًا حتى لا يتداخلا
        pressed = hub.buttons.pressed()
        if pressed and (rc_driving or rc_arm_driving):
            rc_halt_and_wait()
        if pressed and run_active:
            run_cancel("زر من الهاب")
            wait_for_release()      # لا ننفّذ وظيفة الزر بعد إلغاء التنفيذ
            pressed = ()

        if Button.LEFT in pressed and Button.RIGHT in pressed:
            do_undo()
            wait_for_release()

        elif Button.CENTER in pressed and Button.LEFT in pressed:
            do_find_line_point()
            wait_for_release()

        elif Button.CENTER in pressed and Button.RIGHT in pressed:
            do_follow_line_seg()
            wait_for_release()

        elif Button.RIGHT in pressed:
            do_record_move()
            wait_for_release()

        elif Button.LEFT in pressed:
            do_read_sensors()
            wait_for_release()

        elif Button.CENTER in pressed:
            do_print_program()
            wait_for_release()

        # 3) تنفيذ دورة واحدة من التحكم عن بعد (تسارع محدود + إيقاف تلقائي)
        rc_tick()

        # 3.5) تنفيذ دورة واحدة من الكود المستلم من التطبيق (دفعات صغيرة)
        run_tick()

        # 4) قراءة الحساسات تلقائيًا (جمع عينات + بثّ أثناء الحركة)
        auto_read_tick()

        # أثناء استلام الكود نُسرّع الدورة (10ms) حتى نفرّغ مخزن الإدخال
        # أسرع من وصول الأسطر من التطبيق، فلا يضيع أي حرف
        wait(10 if code_mode else 30)

finally:
    hub.light.on(Color.RED)
    rc_stop()
    left_motor.stop()
    right_motor.stop()
    if arm_motor is not None:
        arm_motor.stop()
