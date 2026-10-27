from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, ColorSensor
from pybricks.parameters import Port, Button, Direction, Color
from pybricks.robotics import DriveBase
from pybricks.tools import wait

# =========================================================
# 1) المنافذ حسب روبوتك
# =========================================================
hub = PrimeHub()

left_motor  = Motor(Port.A, Direction.COUNTERCLOCKWISE)  # عدّل الاتجاه إذا لزم
right_motor = Motor(Port.B)

# محرك إضافي (ذراع / بوابة / مهام) على المنفذ D
ARM_PORT        = Port.D
ARM_PORT_LETTER = "D"          # يُطبع في البرنامج الناتج
arm_motor = Motor(ARM_PORT)

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

    print("")
    print("# " + "=" * 50)
    print("# برنامج السباق الذكي (" + str(n_cmds) + " أمر مسجّل) - انسخ كل ما يلي:")
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

def print_sensor(name, s):
    c = s.color()
    r = s.reflection()
    a = s.ambient()
    hsv = s.hsv()
    line = "# " + name + ": color=" + str(c) + ", reflection=" + str(r) + ", ambient=" + str(a) + ", hsv=" + str(hsv)
    print(line)
    return line, r

# =========================================================
# 5) البرنامج الرئيسي: توليد كود ذكي من التدريب
# =========================================================
for line in setup_lines(False):
    print(line)

left_motor.stop()   # coast: تُترك المحركات حرة ليُدفع الروبوت باليد
right_motor.stop()
arm_motor.stop()    # coast: يُترك محرك المنفذ D حراً لتحريك الذراع باليد
arm_motor.reset_angle(0)

robot.reset()  # تصفير عدادات المسافة والزاوية (والجيرو)

last_distance  = robot.distance()
last_heading   = hub.imu.heading()
last_arm_angle = arm_motor.angle()

hub.light.on(Color.BLUE)
print("")
print("# جاهز:")
print("# حرّك الروبوت بيدك ثم اضغط:")
print("# - RIGHT       : تسجيل حركة (دوران ثم مستقيم + محرك D)")
print("# - LEFT        : تسجيل قراءة الحسّاس (لحساب عتاة الخط)")
print("# - CENTER+LEFT : نقطة خط ذكية find_line (+ محاذاة) بدل آخر مستقيم")
print("# - CENTER+RIGHT: مقطع متابعة خط follow_line بآخر مسافة")
print("# - LEFT+RIGHT  : حذف آخر تسجيل (مع إرجاع نقطة القياس)")
print("# - CENTER      : طباعة برنامج السباق الذكي الكامل")

try:
    while True:
        pressed = hub.buttons.pressed()

        if Button.LEFT in pressed and Button.RIGHT in pressed:
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
            wait_for_release()

        elif Button.CENTER in pressed and Button.LEFT in pressed:
            # نقطة خط ذكية: يستبدل الحركة منذ آخر تسجيل ببحث دقيق عن الخط.
            #   بالحسّاس الواحد لا نضيف محاذاة بعد find_line: الحسّاس يكون
            #   على الخط مباشرة بعد البحث، فالمحاذاة تصبح بلا أثر.
            curr_distance = robot.distance()
            curr_heading  = hub.imu.heading()
            diff_dist = curr_distance - last_distance
            diff_head = curr_heading - last_heading

            refl.add(line_sensor.reflection())

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
                last_heading  = curr_heading
                hub.speaker.beep(500, 80)
            wait_for_release()

        elif Button.CENTER in pressed and Button.RIGHT in pressed:
            # مقطع متابعة خط: يتبع الحافة بآخر مسافة مجرَّبة
            curr_distance = robot.distance()
            curr_heading  = hub.imu.heading()
            diff_dist = curr_distance - last_distance
            diff_head = curr_heading - last_heading

            refl.add(line_sensor.reflection())

            segs = []
            if abs(diff_head) >= MIN_ANG:
                segs.append(("turn", int(round(diff_head))))

            if abs(diff_dist) >= MIN_DIST:
                # الجانب من الثابت FOLLOW_SIDE (لا مقارنة حساسين بعد الآن)
                segs.append(("follow_line", (int(round(abs(diff_dist))), FOLLOW_SIDE)))

            if segs:
                if push_action("move", segs, last_distance, last_heading, last_arm_angle):
                    for seg in segs:
                        print(format_seg(seg))
                    last_distance = curr_distance
                    last_heading  = curr_heading
                    hub.speaker.beep(550, 80)
            else:
                print("# حركة أصغر من العتبة - تم تجاهلها")
            wait_for_release()

        elif Button.RIGHT in pressed:
            curr_distance = robot.distance()
            curr_heading  = hub.imu.heading()
            curr_arm      = arm_motor.angle()

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

            wait_for_release()

        elif Button.LEFT in pressed:
            line, ref = print_sensor("LINE sensor (Port." + LINE_PORT_LETTER + ")", line_sensor)
            refl.add(ref)
            push_action("sensor", [line])
            hub.speaker.beep(750, 80)
            wait_for_release()

        elif Button.CENTER in pressed:
            try:
                print_full_program()
            except MemoryError:
                # فشل الذاكرة أثناء الطباعة: بدل انتهاء البرنامج كله
                print("# ⚠ نفد ذاكرة الهاب: لم يكتمل طباعة البرنامج")
                print("#   احذف بعض التسجيلات (LEFT+RIGHT) ثم أعد الطباعة (CENTER)")
                hub.speaker.beep(250, 250)
                wait_for_release()
                continue
            hub.speaker.beep(900, 150)
            wait_for_release()

        wait(30)

finally:
    hub.light.on(Color.RED)
    left_motor.stop()
    right_motor.stop()
    arm_motor.stop()
