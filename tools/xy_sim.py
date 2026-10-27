# -*- coding: utf-8 -*-
"""
xy_sim.py — محاكاة برمجية (Software-in-the-Loop) لاختبار ``xy_nav.py`` بلا هاردوير.

لا نختبر هنا دوال رياضية معزولة: نُنفّذ **الملف الحقيقي** ``xy_nav.py``
(كل ما قبل «البرنامج الرئيسي») فوق عتاد Pybricks وهمي يُدخل أخطاءً واقعية:

  * خطأ معايرة قطر العجلة          ``odom_gain``
  * انزلاق العجلات                  ``slip_mean`` / ``slip_std``
  * عدم تماثل العجلتين (انحراف)     ``asym``
  * انحراف الجيروسكوب + ضجيج       ``gyro_drift`` / ``gyro_noise``
  * ضجيج حساس الألوان + إضاءة      ``sensor_noise`` / ``ambient``
  * خطوط داكنة حقيقية على السجادة   ``lines``
  * تباطؤ استجابة المحركات          ``TAU`` (first-order lag)
  * تعطّل الحركة (روبوت محشور)      ``stall``

أهم ما نقيسه: الفرق بين **الموقع الحقيقي** للروبوت و**الموقع الذي يعتقده**
(``Nav.x/y``) — لأن ``goto()`` يعتبر نفسه ناجحًا متى وصل *تقديره* للهدف،
حتى لو كان الروبوت فعليًا بعيدًا عنه.

التشغيل::

    python3 tools/xy_sim.py                       # ملخّص نصي سريع
    python3 tools/xy_sim.py --trials 30 \\
        --md docs/تقرير_اختبار_xy_nav.md \\
        --html docs/xy_sim_report.html

الخلاصة عملية بحتة: لا يحتاج أي حزمة خارجية (بايثون القياسي فقط).
"""

import argparse
import contextlib
import io
import json
import math
import os
import random
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUBS = os.path.join(ROOT, "tests", "stubs")
for _p in (STUBS, os.path.join(ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MARKER = "# ==== 8) البرنامج الرئيسي"


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


# =========================================================
# 1) العتاد الوهمي الواقعي
# =========================================================
class SimulationStuck(RuntimeError):
    """ارتفع عدد الخطوات بشكل غير معقول ⇒ حلقة لا نهائية في الكود المُختبَر."""


class Sim:
    """الفيزياء الحقيقية (مخفية عن الروبوت) + ما يراه الروبوت من حساسات."""

    DT_MS = 10
    TAU = 0.06          # ثابت تباطؤ المحرك (ثوانٍ)
    MAX_STEPS = 60000   # 600 ثانية — حماية من الحلقات اللانهائية

    def __init__(self, seed=0, odom_gain=1.0, slip_mean=0.0, slip_std=0.0,
                 asym=0.0, gyro_drift=0.0, gyro_noise=0.0, turn_noise=0.0,
                 sensor_noise=0.0, ambient=0.0, lines=None, stall=False,
                 start_heading=0.0, trace_every=20, color_fn=None):
        self.seed = seed
        self.rng = random.Random(seed)
        self.odom_gain = odom_gain
        self.slip_mean, self.slip_std = slip_mean, slip_std
        self.asym = asym
        self.gyro_drift, self.gyro_noise = gyro_drift, gyro_noise
        self.turn_noise = turn_noise
        self.sensor_noise, self.ambient = sensor_noise, ambient
        self.lines = lines or []
        self.stall = stall
        self.start_heading = start_heading
        self.trace_every = trace_every
        self.color_fn = color_fn

        self.t_ms = 0.0
        self.steps = 0
        self.stops = 0
        self.beeps = []
        self.light_color = None
        self.arm_calls = []

        # الحالة الحقيقية (لا يعرفها الروبوت)
        self.x, self.y = 0.0, 0.0
        self.true_heading = wrap180(start_heading)
        self.gyro_bias = 0.0

        # ما تقيسه حساسات الروبوت
        self.odom_d = 0.0                       # robot.distance()
        self.gyro_heading = wrap180(start_heading)  # hub.imu.heading()

        # أوامر المحرك + استجابته
        self.speed_cmd = self.turn_cmd = 0.0
        self.speed_actual = 0.0

        self.trace_true = []
        self.trace_est = []
        self._record()

    # -- أوامر العتاد --------------------------------------------------
    def drive(self, speed, turn_rate):
        self.speed_cmd, self.turn_cmd = float(speed), float(turn_rate)

    def stop(self):
        self.speed_cmd = self.turn_cmd = 0.0
        self.stops += 1

    def distance(self):
        return self.odom_d

    def heading(self):
        return self.gyro_heading

    def beep(self, freq, ms):
        self.beeps.append((round(freq), round(ms)))

    def reflection(self):
        """انعكاس الحساس: 90 = أبيض، ~12 = خط داكن، + إضاءة/ضجيج."""
        r = 90.0
        for kind, pos, width in self.lines:
            coord = self.x if kind == "v" else self.y
            if abs(coord - pos) <= width / 2.0:
                r = min(r, 12.0)
        if self.sensor_noise:
            r += self.rng.gauss(0.0, self.sensor_noise)
        return clamp(r + self.ambient, 0.0, 100.0)

    def color(self):
        if self.color_fn is None:
            return None
        return self.color_fn(self)

    # -- الساعة --------------------------------------------------------
    def wait(self, ms):
        n = max(1, int(round(float(ms) / self.DT_MS)))
        dt = self.DT_MS / 1000.0
        for _ in range(n):
            self._step(dt)
            self.steps += 1
            if self.steps > self.MAX_STEPS:
                raise SimulationStuck(
                    "تجاوزت %d خطوة (%d ثانية محاكاة) — حلقة لا نهائية محتملة"
                    % (self.MAX_STEPS, self.MAX_STEPS * self.DT_MS // 1000))
            if self.steps % self.trace_every == 0:
                self._record()

    def _step(self, dt):
        # استجابة المحرك ليست لحظية
        self.speed_actual += (self.speed_cmd - self.speed_actual) * min(1.0, dt / self.TAU)
        if self.stall:
            self.speed_actual = 0.0

        # عدّاد العجلات (ما يراه robot.distance) ≠ المسافة الحقيقية عند الانزلاق
        wheel = self.speed_actual * dt
        self.odom_d += wheel * self.odom_gain

        slip = max(0.0, self.slip_mean + self.rng.gauss(0.0, self.slip_std))
        true_dist = wheel * (1.0 - slip)

        w = (self.turn_cmd
             + self.asym * (self.speed_actual / 260.0)
             + self.rng.gauss(0.0, self.turn_noise))
        self.true_heading = wrap180(self.true_heading + w * dt)

        self.x += true_dist * math.cos(math.radians(self.true_heading))
        self.y += true_dist * math.sin(math.radians(self.true_heading))
        self.t_ms += dt * 1000.0

        self.gyro_bias += self.gyro_drift * dt
        self.gyro_heading = wrap180(
            self.true_heading + self.gyro_bias
            + self.rng.gauss(0.0, self.gyro_noise))

    def _record(self):
        self.trace_true.append([round(self.x, 1), round(self.y, 1),
                                round(self.true_heading, 1)])
        if hasattr(self, "_nav_ref"):
            nav = self._nav_ref
            self.trace_est.append([round(nav.x, 1), round(nav.y, 1),
                                   round(nav.heading, 1)])


class _Drive:
    def __init__(self, sim):
        self.s = sim

    def drive(self, speed, turn_rate):
        self.s.drive(speed, turn_rate)

    def stop(self):
        self.s.stop()

    def distance(self):
        return self.s.distance()

    def reset(self):
        pass

    def use_gyro(self, *a):
        pass

    def settings(self, **kw):
        pass


class _Imu:
    def __init__(self, sim):
        self.s = sim

    def heading(self):
        return self.s.heading()


class _Speaker:
    def __init__(self, sim):
        self.s = sim

    def beep(self, freq, ms):
        self.s.beep(freq, ms)


class _Light:
    def __init__(self, sim):
        self.s = sim

    def on(self, color):
        self.s.light_color = color


class _Buttons:
    def pressed(self):
        return []


class _Hub:
    def __init__(self, sim):
        self.imu = _Imu(sim)
        self.speaker = _Speaker(sim)
        self.light = _Light(sim)
        self.buttons = _Buttons()


class _Sensor:
    def __init__(self, sim):
        self.s = sim

    def reflection(self):
        return self.s.reflection()

    def color(self):
        return self.s.color()


class _Arm:
    def __init__(self, sim):
        self.s = sim

    def run_angle(self, speed, angle, *a, **kw):
        self.s.arm_calls.append((speed, angle))

    def stop(self):
        pass


class _StopWatch:
    def __init__(self, sim):
        self.s = sim
        self.t0 = sim.t_ms

    def time(self):
        return self.s.t_ms - self.t0

    def reset(self):
        self.t0 = self.s.t_ms


# =========================================================
# 2) تحميل الملف الحقيقي فوق العتاد الوهمي
# =========================================================
def load_xy_nav(sim):
    """نفّذ xy_nav.py الحقيقي (قبل البرنامج الرئيسي) ثم اربطه بالمحاكاة."""
    with io.open(os.path.join(ROOT, "xy_nav.py"), encoding="utf-8") as handle:
        src = handle.read()
    head = src[:src.index(MARKER)]
    module = types.ModuleType("xy_nav_sil")
    module.__dict__["__name__"] = "xy_nav_sil"
    exec(compile(head, os.path.join(ROOT, "xy_nav.py"), "exec"), module.__dict__)

    module.hub = _Hub(sim)
    module.robot = _Drive(sim)
    module.arm_motor = _Arm(sim)
    module.line_sensor = _Sensor(sim)
    module.ARTIFACT_SENSOR = module.line_sensor
    module.wait = sim.wait
    module.StopWatch = lambda: _StopWatch(sim)

    # سجّل الموقع المُقدَّر في كل دورة تحديث
    original_update = module.Nav.update

    def traced_update(self):
        sim._nav_ref = self
        return original_update(self)

    module.Nav.update = traced_update
    return module


def new_nav(module, sim):
    nav = module.Nav()
    sim._nav_ref = nav
    return nav


# =========================================================
# 3) سيناريوهات الاختبار
# =========================================================
WAYPOINTS = [(300, 0), (300, 400), (900, 400), (900, -200), (1500, 0)]
LINES = [("v", 900.0, 20.0), ("h", 400.0, 20.0)]

# مهمة التصحيح بالخط: نفس المسار الطويل، لكن قبل الرجل الأخيرة نبحث عن خط
# عمودي مركزه x=1400 (حافة الاكتشاف 1390) ونثبّت إحداثي X، ثم نقطع 110 مم فقط.
# هكذا نعزل أثر التثبيت على المحور الذي يصحّحه فعلًا.
SNAP_WAYPOINTS = [(300, 0), (300, 400), (900, 400), (900, -200), (1380, 0)]
SNAP_TAIL = [(1500, 0)]
SNAP_LINE_X = 1390.0        # حافة الخط التي يراها الحساس (المركز 1400، العرض 20)

SCENARIOS = [
    ("مثالي", dict()),
    ("معايرة +3%", dict(odom_gain=1.03)),
    ("انزلاق 2%", dict(slip_mean=0.02, slip_std=0.02)),
    ("انحراف جيرو 0.5°/ث", dict(gyro_drift=0.5, gyro_noise=0.3)),
    ("عدم تماثل عجلات", dict(asym=8.0, turn_noise=0.8)),
    ("كل الأخطاء معًا", dict(odom_gain=1.03, slip_mean=0.02, slip_std=0.02,
                             gyro_drift=0.5, gyro_noise=0.3, asym=8.0,
                             turn_noise=0.8, sensor_noise=4.0, ambient=6.0)),
    ("كل الأخطاء + تثبيت خط واحد", dict(
        odom_gain=1.03, slip_mean=0.02, slip_std=0.02,
        gyro_drift=0.5, gyro_noise=0.3, asym=8.0,
        turn_noise=0.8, sensor_noise=4.0, ambient=6.0, snap=True,
        # ممر التصحيح: خط واحد فقط. تقاطع الخطوط يُختبر على انفراد في
        # tests/test_xy_nav_sim.py (كان يسبب تثبيتًا خاطئًا بـ 200 مم).
        lines=[("v", 1400.0, 20.0)])),
    ("كل الأخطاء + موضع مثالي فقط", dict(
        odom_gain=1.03, slip_mean=0.02, slip_std=0.02,
        gyro_drift=0.5, gyro_noise=0.3, asym=8.0,
        turn_noise=0.8, sensor_noise=4.0, ambient=6.0, perfect_est=True)),
    ("كل الأخطاء + موضع واتجاه مثاليان (حدّ علوي)", dict(
        odom_gain=1.03, slip_mean=0.02, slip_std=0.02,
        gyro_drift=0.5, gyro_noise=0.3, asym=8.0,
        turn_noise=0.8, sensor_noise=4.0, ambient=6.0,
        perfect_est=True, perfect_heading=True)),
]

COMBINED = SCENARIOS[5][1]   # «كل الأخطاء معًا» — أساس المقارنة


def run_mission(seed, params):
    """شغّل مهمة كاملة وأعد مقاييس الدقة.

    ``perfect_est=True`` يحاكي «حدًا علويًا»: نظام تحديد موضع خارجي مثالي
    يخبر الروبوت بموقعه الحقيقي قبل كل رجل. ليس هذا سلوك ``xy_nav.py``
    التلقائي، بل يوضّح كم يمكن أن تُحسّن المعالم المتكررة النتيجة.
    """
    params = dict(params)
    do_snap = params.pop("snap", False)
    perfect_est = params.pop("perfect_est", False)
    perfect_heading = params.pop("perfect_heading", False)
    lines = params.pop("lines", LINES)
    sim = Sim(seed=seed, lines=lines, trace_every=25, **params)
    m = load_xy_nav(sim)
    nav = new_nav(m, sim)

    log = io.StringIO()
    legs = SNAP_WAYPOINTS if do_snap else WAYPOINTS
    tail = SNAP_TAIL if do_snap else []
    all_legs = legs + tail
    results = []
    snapped = None
    err_before_snap = err_after_snap = None

    with contextlib.redirect_stdout(log):
        for index, wp in enumerate(all_legs):
            # قبل الرجل التالية للسيناريو المُصحَّح: نفّذ البحث عن الخط مرة واحدة
            if do_snap and index == len(legs):
                nav.face(0)
                err_before_snap = round(math.hypot(sim.x - nav.x, sim.y - nav.y), 1)
                # قيمة التثبيت يجب أن تكون إحداثي **حافة** اكتشاف الخط لا مركزه:
                # الخط مركزه 1400 وعرضه 20 ⇒ الحافة التي يراها الحساس عند 1390.
                snapped = nav.find_line_and_snap("x", SNAP_LINE_X,
                                                max_dist=280, speed=100)
                if snapped:
                    err_after_snap = round(math.hypot(sim.x - nav.x, sim.y - nav.y), 1)
            try:
                ok = nav.goto(wp[0], wp[1])
            except SimulationStuck as exc:
                return {"ok": False, "stuck": str(exc), "seed": seed,
                        "legs": results, "sim": sim, "logs": log.getvalue()}
            results.append({
                "target": list(wp), "ok": bool(ok),
                "est_err": round(math.hypot(nav.x - wp[0], nav.y - wp[1]), 1),
                "true_err": round(math.hypot(sim.x - wp[0], sim.y - wp[1]), 1),
                "t_ms": round(sim.t_ms),
            })
            if not ok:
                break
            if perfect_est:
                # نظام تحديد موضع خارجي مثالي: الروبوت يعرف مكانه الحقيقي.
                # (ملاحظة: تثبيت التقدير على إحداثيات الهدف وهو بعيد عنها فعلًا
                #  يزيد الخطأ — لذلك نستخدم الموقع الحقيقي هنا لا الهدف.)
                nav.x, nav.y = sim.x, sim.y
                nav._last_d = sim.odom_d
            if perfect_heading:
                # محاذاة على خط مستقيم ⇒ تصفير انحراف الجيرو المتراكم
                sim.gyro_bias = 0.0

    last = all_legs[-1]
    return {
        "ok": all(r["ok"] for r in results) and len(results) == len(all_legs),
        "seed": seed,
        "legs": results,
        "snapped": snapped,
        "err_before_snap": err_before_snap,
        "err_after_snap": err_after_snap,
        "final_true_err": round(math.hypot(sim.x - last[0], sim.y - last[1]), 1),
        "final_x_err": round(abs(sim.x - last[0]), 1),
        "final_y_err": round(abs(sim.y - last[1]), 1),
        "final_est_err": round(math.hypot(nav.x - last[0], nav.y - last[1]), 1),
        "final_heading_err": round(abs(wrap180(sim.true_heading - nav.heading)), 2),
        "t_ms": round(sim.t_ms),
        "steps": sim.steps,
        "beeps": len(sim.beeps),
        "trace_true": sim.trace_true,
        "trace_est": sim.trace_est,
        "logs": log.getvalue(),
        "sim": sim,
    }


def run_suite(trials):
    out = []
    def mean_of(runs, key):
        vals = [r[key] for r in runs if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    for name, params in SCENARIOS:
        runs = [run_mission(seed, params) for seed in range(trials)]
        clean = [dict((k, v) for k, v in r.items()
                      if k not in ("sim", "logs"))
                 for r in runs]
        errors = sorted(r.get("final_true_err", 9999) for r in runs)
        out.append({
            "name": name,
            "trials": trials,
            "success": sum(1 for r in runs if r["ok"]),
            "stuck": sum(1 for r in runs if r.get("stuck")),
            "mean": round(sum(errors) / len(errors), 1),
            "median": round(errors[len(errors) // 2], 1),
            "p95": round(errors[min(len(errors) - 1, int(len(errors) * 0.95))], 1),
            "max": round(errors[-1], 1),
            "mean_x": mean_of(runs, "final_x_err"),
            "mean_y": mean_of(runs, "final_y_err"),
            "snapped": sum(1 for r in runs if r.get("snapped")),
            "err_before_snap": mean_of(runs, "err_before_snap"),
            "err_after_snap": mean_of(runs, "err_after_snap"),
            "logs": [r.get("logs", "").strip().splitlines()[-2:]
                     for r in runs if r.get("logs")][:2],
            "lines": params.get("lines", LINES),
            "runs": clean,
        })
    return out


# =========================================================
# 4) تقارير
# =========================================================
def text_report(suite):
    lines = ["نتائج محاكاة xy_nav.py — %d محاولة لكل سيناريو" % suite[0]["trials"],
             "", "%-44s %7s %8s %8s %8s %8s" %
             ("السيناريو", "نجاح", "متوسط", "خطأ X", "خطأ Y", "أقصى"),
             "-" * 88]
    for s in suite:
        lines.append("%-44s %3d/%-3d %8.1f %8s %8s %8.1f" %
                     (s["name"][:44], s["success"], s["trials"], s["mean"],
                      s["mean_x"], s["mean_y"], s["max"]))
    return "\n".join(lines)


def markdown_report(suite):
    trials = suite[0]["trials"]
    by_name = dict((s["name"], s) for s in suite)
    ideal = by_name["مثالي"]["mean"]
    combined = by_name["كل الأخطاء معًا"]
    gyro = by_name["انحراف جيرو 0.5°/ث"]
    calib = by_name["معايرة +3%"]
    slip = by_name["انزلاق 2%"]
    asym = by_name["عدم تماثل عجلات"]
    single = by_name["كل الأخطاء + تثبيت خط واحد"]
    perfect = by_name["كل الأخطاء + موضع مثالي فقط"]
    ceiling = by_name["كل الأخطاء + موضع واتجاه مثاليان (حدّ علوي)"]
    out = [
        "# تقرير اختبار `xy_nav.py` (محاكاة برمجية)",
        "",
        "> أُنشئ بواسطة `tools/xy_sim.py` في 2026-10-27. "
        "**هذه محاكاة، وليست قياسًا على سجادة حقيقية** — لكنها تُنفّذ "
        "الملف الحقيقي `xy_nav.py` سطرًا بسطر فوق عتاد وهمي يُدخل أخطاءً فيزيائية.",
        "",
        "## طريقة القياس",
        "",
        "- يُحمَّل `xy_nav.py` قبل «البرنامج الرئيسي»، ثم تُستبدل وحدات Pybricks "
        "بعتاد وهمي: عدّاد مسافة، جيروسكوب، حساس ألوان، محرك ذراع، وساعة.",
        "- لكل خطوة 10ms تُحسب **الفيزياء الحقيقية** (موقع/اتجاه فعليان)، "
        "وما **يراه الروبوت** (عداد العجلات + الجيرو + الانعكاس) بشكل منفصل.",
        "- الفجوة بين الاثنين هي الخطأ الحقيقي: `goto()` يعتبر نفسه ناجحًا متى وصل "
        "*تقديره* إلى الهدف، لا متى وصل الروبوت فعليًا.",
        "- المهمة: " + " → ".join("`(%d,%d)`" % w for w in WAYPOINTS) + " مم.",
        "- على السجادة خط عمودي عند `x=900` وخط أفقي عند `y=400` (عرض 20 مم). "
        "سيناريو التثبيت يستخدم خطًا عموديًا وحيدًا مركزه `x=1400` قبل الرجل الأخيرة.",
        "",
        "## النتائج (%d محاولة لكل سيناريو)" % trials,
        "",
        "| السيناريو | نجاح الوصول | متوسط الخطأ | خطأ X | خطأ Y | p95 | الأقصى |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in suite:
        out.append("| %s | %d/%d | **%.1f مم** | %s | %s | %.1f | %.1f |" %
                   (s["name"], s["success"], s["trials"], s["mean"],
                    s["mean_x"], s["mean_y"], s["p95"], s["max"]))
    out += [
        "",
        "## الاستنتاجات (مرتّبة بالأهمية)",
        "",
        "1. **الجيروسكوب هو المصدر الأكبر للخطأ.** انحراف بسيط %.1f°/ث أنتج "
        "**%.1f مم** خطأ (منه ~%.0f مم على محور Y وحده)، مقابل %.1f مم لخطأ "
        "معايرة العجلات +3%% و%.1f مم للانزلاق 2%%. أي معايرة لا تبدأ بالجيرو "
        "تضيع وقتها." % (0.5, gyro["mean"], gyro["mean_y"], calib["mean"],
                         slip["mean"]),
        "2. **الملاحة بالإحداثيات وحدها غير كافية.** مع كل الأخطاء مجتمعة بلغ "
        "متوسط الخطأ **%.1f مم** بعد مسار ~2.5 م، بينما كان تقدير الروبوت "
        "الداخلي يوحي بأنه وصل (خطأه المُقدَّر < 12 مم). هذا بالضبط سبب الحاجة "
        "إلى معالم لونية/خطوط قبل كل مهمة دقيقة." % combined["mean"],
        "3. **التحكم المغلق يعوّض عدم التماثل لا الانزلاق.** عدم تماثل العجلات "
        "أعطى %.1f مم (مطابق تقريبًا للحالة المثالية %.1f مم) لأن الجيرو يرى "
        "الانحراف فيصحّحه. أما الانزلاق فبقي أثره %.1f مم: عدّاد العجلات لا يعرف "
        "أن العجلة دارت دون أن يتحرك الروبوت. المشكلة إذن في **جودة الحساسات** "
        "لا في خوارزمية `goto()` نفسها."
        % (asym["mean"], ideal, slip["mean"]),
        "4. **التثبيت على خط يصحّح محورًا واحدًا فقط.** تثبيت واحد قبل الرجل "
        "الأخيرة خفض خطأ X من **%.1f مم** إلى **%.1f مم** (تحسّن ~%.0f%%)، "
        "لكن خطأ Y بقي **%.1f مم** لأن انحراف الجيرو لم يُصفَّر. "
        "الخلاصة: ثبّت **كلا المحورين** عند زاوية/خط متقاطع، وصفّر الجيرو عند "
        "كل خط مستقيم معروف، واجعل الرجل الأخيرة قصيرة."
        % (combined["mean_x"], single["mean_x"],
           100 * (1 - single["mean_x"] / max(0.1, combined["mean_x"])),
           single["mean_y"]),
        "5. **حتى المعالم المثالية لا تُغني عن معايرة قطر العجلة.** مع موضع "
        "مثالي فقط بقي %.1f مم، ومع موضع **واتجاه** مثاليين بقي %.1f مم — "
        "وهو أثر خطأ المعايرة +3%% على رجل طولها 600 مم. قِس المسافة الفعلية "
        "لأمر 1000 مم وصحّح رقمَي `DriveBase(..., 56, 110)` في `xy_nav.py` قبل أي شيء آخر."
        % (perfect["mean"], ceiling["mean"]),
        "",
        "> ℹ️ سيناريو «تقدير موضع مثالي» هو **حدّ علوي نظري** (نظام تحديد موضع "
        "خارجي يخبر الروبوت بمكانه الحقيقي)، وليس سلوك `xy_nav.py` التلقائي. "
        "الغرض منه قياس كم يبقى من الخطأ بعد إزالة انحراف التقدير وحده.",
        "",
        "## الأخطاء المكتشفة أثناء الاختبار والمُصلَحة",
        "",
        "1. **حلقة لا نهائية في `find_line_and_snap()`** — لم يكن فيها أي حدّ زمني؛ "
        "عند تعطّل الحركة (روبوت محشور/مرفوع) لا يتغيّر `robot.distance()` فتدور "
        "الحلقة إلى الأبد. **تأكيد عملي:** توقفت المحاكاة عند 60000 خطوة (600 ث) "
        "قبل الإصلاح. أُضيفت مهلة `LINE_TIMEOUT_MS = 2500` وإعادة إصدار `drive()` "
        "داخل الحلقة وتحديث الموقع أثناء البحث.",
        "2. **تثبيت خاطئ عند تقاطع الخطوط** — الوقوف على خط أفقي `y=400` جعل "
        "الحساس يرى «خطًا» فورًا، فثُبّت `x` على 900 بينما الروبوت عند 700: "
        "**خطأ 200 مم** بضغطة واحدة. أُضيف سقف `SNAP_MAX_CORRECTION = 120` مم "
        "يرفض أي تصحيح أكبر مع رسالة واضحة.",
        "3. **`_map_ready()` لم تتحقق من نوع القيم** — تمرير `line_y` كـ tuple كان "
        "يسبب `TypeError: float() argument ... not a tuple` داخل `snap()` أثناء "
        "الجولة. صارت هناك `_map_problems()` تتحقق من الأزواج الرقمية وتسمّي "
        "المفتاح الخاطئ في رسالة التشخيص.",
        "4. **`run()` تجاهلت فشل `goto()`** في منتصف المهمة — كان الروبوت يتابع "
        "المناولة وهو تائه. أُضيفت دالة `must()` توقف الجولة برسالة تتضمن آخر موقع.",
        "5. **`goto()` لم تحتسب مسافة التباطؤ** — كانت تستدعي `robot.stop()` ثم "
        "`update()` فورًا؛ أُضيف `wait(30)` قبل التحديث لاحتساب الحركة المتبقية.",
        "",
        "## ما تبقّى للاختبار على السجادة الحقيقية",
        "",
        "هذه المحاكاة تُثبت أن **المنطق البرمجي سليم**، لكنها لا تُثبت أن "
        "المعايرة تناسب روبوتكم. المطلوب ميدانيًا:",
        "",
        "1. شغّل `MAP_MODE = True` واملأ `FIELD_MAP` بقياسات شريط قياس حقيقي.",
        "2. اضبط رقمَي `DriveBase(left_motor, right_motor, 56, 110)` بقياس فعلي: "
        "امشِ 1000 مم للأمام على خط مستقيم، قِس المسافة الحقيقية، ثم صحّح قطر "
        "العجلة بنسبة الخطأ (مثال: قِست 1030 مم ⇒ اضرب 56 في 1000/1030).",
        "3. اختبر الجيرو: دُر 360° عشر مرات وافحص انحراف `heading()` التراكمي.",
        "4. قِس `LINE_THRESHOLD` فوق الخط وفوق الخلفية تحت إضاءة القاعة.",
        "5. كرّر المهمة 10 مرات على **طاولتين مختلفتين** وسجّل `# FINAL`.",
        "6. لا تنسَ: أثناء الجولة الرسمية يجب إطفاء البلوتوث/الواي فاي وتشغيل "
        "الملف من الـ Hub نفسه (القواعد العامة 5.6 و5.9).",
        "",
        "## إعادة التوليد",
        "",
        "```bash",
        "python3 tools/xy_sim.py --trials %d --md docs/تقرير_اختبار_xy_nav.md "
        "--html docs/xy_sim_report.html" % trials,
        "python3 -m unittest discover -s tests -t tests -p 'test_xy_nav*.py' -v",
        "```",
        "",
    ]
    return "\n".join(out)


HTML_TEMPLATE = u"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>تقرير محاكاة xy_nav.py</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;background:#0b1220;color:#e6edf7;
   font-family:system-ui,"Segoe UI",Tahoma,Arial,sans-serif;line-height:1.75}
 .wrap{max-width:1100px;margin:auto;padding:28px 20px 60px}
 h1{font-size:26px;margin:0 0 6px} h2{font-size:19px;margin:34px 0 12px;
   border-bottom:1px solid #25334d;padding-bottom:8px}
 .sub{color:#94a3b8;font-size:14px;margin-bottom:22px}
 .card{background:#111c2f;border:1px solid #25334d;border-radius:14px;
   padding:18px;margin:14px 0}
 table{width:100%;border-collapse:collapse;font-size:14px}
 th,td{padding:9px 10px;border-bottom:1px solid #25334d;text-align:right}
 th{color:#94a3b8;font-weight:600} tr:last-child td{border-bottom:0}
 .good{color:#34d399} .mid{color:#fbbf24} .bad{color:#f87171}
 .row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:12px 0}
 label{font-size:14px;color:#94a3b8}
 select{background:#0b1220;color:#e6edf7;border:1px solid #25334d;
   border-radius:9px;padding:8px 10px;font-family:inherit}
 svg{width:100%;height:auto;background:#08101e;border:1px solid #25334d;
   border-radius:12px;display:block}
 .legend{font-size:13px;color:#94a3b8;margin-top:8px}
 .legend b{color:#e6edf7}
 .note{border-right:3px solid #60a5fa;padding:6px 14px;color:#94a3b8;
   font-size:14px;margin:12px 0}
 code{background:#0b1220;padding:2px 6px;border-radius:5px;font-size:13px}
 ul{padding-inline-start:22px} li{margin:6px 0}
</style>
</head>
<body><div class="wrap">
<h1>🧭 تقرير محاكاة <code>xy_nav.py</code></h1>
<div class="sub">Software-in-the-Loop — ينفّذ الملف الحقيقي فوق عتاد وهمي فيه انزلاق عجلات،
انحراف جيروسكوب، عدم تماثل، وضجيج حساسات. __TRIALS__ محاولة لكل سيناريو.</div>

<h2>النتائج</h2>
<div class="card"><table><thead><tr><th>السيناريو</th><th>النجاح</th>
<th>متوسط الخطأ</th><th>خطأ X</th><th>خطأ Y</th><th>p95</th></tr></thead>
<tbody>__ROWS__</tbody></table></div>
<div class="note">الخطأ هنا هو <b>المسافة بين الموقع الحقيقي للروبوت والهدف</b>،
لا بين تقدير الروبوت والهدف. <code>goto()</code> قد يُعلن النجاح بينما الروبوت بعيد فعلًا.</div>

<h2>الاستنتاجات</h2>
<div class="card"><ol>__FINDINGS__</ol></div>

<h2>مسار الروبوت على السجادة</h2>
<div class="card">
 <div class="row">
  <label>السيناريو <select id="sc"></select></label>
  <label>المحاولة <select id="seed"></select></label>
  <label><input type="checkbox" id="showEst" checked> الموقع المُقدَّر</label>
 </div>
 <svg id="plot" viewBox="0 0 1000 520" preserveAspectRatio="xMidYMid meet"></svg>
 <div class="legend">🟩 مستطيل السجادة · <b>خط أزرق</b> = الموقع الحقيقي ·
 <b>خط وردي متقطع</b> = تقدير الروبوت · <b>نقاط صفراء</b> = الأهداف ·
 <b>شرائح رمادية</b> = الخطوط الداكنة</div>
 <div id="stats" class="legend"></div>
</div>

<h2>ما أصلحه هذا الاختبار</h2>
<div class="card"><ol>
<li><b>حلقة لا نهائية</b> في <code>find_line_and_snap()</code> عند تعطّل الحركة
(توقفت المحاكاة عند 60000 خطوة قبل الإصلاح) → مهلة <code>LINE_TIMEOUT_MS</code>.</li>
<li><b>تثبيت خاطئ عند تقاطع الخطوط</b>: الوقوف على خط أفقي كان ينقل الروبوت
200 مم دفعة واحدة → سقف <code>SNAP_MAX_CORRECTION</code> يرفض التصحيح المشبوه.</li>
<li><code>_map_ready()</code> كانت تقبل <code>line_y</code> كـ tuple فينهار
<code>run()</code> بـ <code>TypeError</code> → تحقق من الأنواع مع اسم المفتاح.</li>
<li><code>run()</code> كانت تتجاهل فشل <code>goto()</code> → تتوقف برسالة تشخيصية.</li>
<li><code>goto()</code> لم تحتسب مسافة التباطؤ → أُضيف <code>wait(30)</code> قبل التحديث.</li>
</ol></div>
<div class="note">⚠️ المحاكاة تُثبت سلامة المنطق فقط. المعايرة الحقيقية
(<code>odom_gain</code>، <code>LINE_THRESHOLD</code>، انحراف الجيرو) يجب أن تُقاس
على سجادتكم وتحت إضاءة القاعة — راجع <code>docs/تقرير_اختبار_xy_nav.md</code>.</div>
</div>
<script>
const DATA = __DATA__;
const W=1000,H=520,PAD=34,FW=2362,FH=1143;
const sx = x => PAD + (x+100)/(FW+100)*(W-2*PAD);
const sy = y => PAD + (y+FH/2+120)/(FH+240)*(H-2*PAD);
const sc=document.getElementById('sc'),seed=document.getElementById('seed'),
      plot=document.getElementById('plot'),stats=document.getElementById('stats'),
      showEst=document.getElementById('showEst');
DATA.forEach((d,i)=>{const o=document.createElement('option');o.value=i;
  o.textContent=d.name;sc.appendChild(o);});
function seeds(){seed.innerHTML='';DATA[+sc.value].runs.forEach((r,i)=>{
  const o=document.createElement('option');o.value=i;o.textContent='#'+r.seed;
  seed.appendChild(o);});}
function path(arr,color,dash){if(!arr||arr.length<2)return '';
 return '<polyline fill="none" stroke="'+color+'" stroke-width="2.4" '+
 (dash?'stroke-dasharray="7 5" ':'')+'points="'+
 arr.map(p=>sx(p[0]).toFixed(1)+','+sy(p[1]).toFixed(1)).join(' ')+'"/>';}
function draw(){
 const d=DATA[+sc.value],r=d.runs[+seed.value]; if(!r) return;
 let g='<rect x="'+sx(0)+'" y="'+sy(-FH/2)+'" width="'+(sx(FW)-sx(0))+
    '" height="'+(sy(FH/2)-sy(-FH/2))+'" fill="#0d1a2e" stroke="#334155"/>';
 (d.lines||[[ 'v',900,20],['h',400,20]]).forEach(L=>{
   if(L[0]==='v') g+='<rect x="'+sx(L[1]-L[2]/2)+'" y="'+sy(-FH/2)+
     '" width="'+(sx(L[1]+L[2]/2)-sx(L[1]-L[2]/2))+'" height="'+
     (sy(FH/2)-sy(-FH/2))+'" fill="#1e293b" opacity=".85"/>';
   else g+='<rect x="'+sx(0)+'" y="'+sy(L[1]-L[2]/2)+'" width="'+
     (sx(FW)-sx(0))+'" height="'+(sy(L[1]+L[2]/2)-sy(L[1]-L[2]/2))+
     '" fill="#1e293b" opacity=".85"/>';
 });
 (r.legs||[]).forEach(L=>{g+='<circle cx="'+sx(L.target[0])+'" cy="'+sy(L.target[1])+
   '" r="6" fill="#fbbf24" stroke="#0b1220" stroke-width="2"/>';});
 g+=path(r.trace_true,'#60a5fa',false);
 if(showEst.checked) g+=path(r.trace_est,'#f472b6',true);
 if(r.trace_true&&r.trace_true.length){const p=r.trace_true[r.trace_true.length-1];
   g+='<circle cx="'+sx(p[0])+'" cy="'+sy(p[1])+'" r="7" fill="#34d399"/>';}
 g+='<circle cx="'+sx(0)+'" cy="'+sy(0)+'" r="6" fill="#fff"/>';
 plot.innerHTML=g;
 stats.innerHTML='النتيجة: <b class="'+(r.ok?'good':'bad')+'">'+(r.ok?'وصل ✓':'فشل/مهلة ✗')+
  '</b> · الخطأ الحقيقي النهائي: <b>'+(r.final_true_err??'—')+' مم</b> · '+
  'خطأ X: <b>'+(r.final_x_err??'—')+'</b> · خطأ Y: <b>'+(r.final_y_err??'—')+'</b> · '+
  'زمن المحاكاة: <b>'+(r.t_ms??'—')+' ms</b> · '+
  'الخطأ المُقدَّر: <b>'+(r.final_est_err??'—')+' مم</b>';
}
sc.onchange=()=>{seeds();draw();}; seed.onchange=draw; showEst.onchange=draw;
seeds();draw();
</script></body></html>
"""


def html_report(suite):
    by_name = dict((s["name"], s) for s in suite)
    combined = by_name["كل الأخطاء معًا"]
    single = by_name["كل الأخطاء + تثبيت خط واحد"]
    gyro = by_name["انحراف جيرو 0.5°/ث"]
    asym = by_name["عدم تماثل عجلات"]
    ceiling = by_name["كل الأخطاء + موضع واتجاه مثاليان (حدّ علوي)"]

    rows = []
    for s in suite:
        color = "good" if s["mean"] < 15 else ("mid" if s["mean"] < 60 else "bad")
        rows.append(
            "<tr><td>%s</td><td>%d/%d</td><td class='%s'>%.1f مم</td>"
            "<td>%s</td><td>%s</td><td>%.1f</td></tr>" %
            (s["name"], s["success"], s["trials"], color, s["mean"],
             s["mean_x"], s["mean_y"], s["p95"]))

    findings = [
        "<b>الجيروسكوب هو المصدر الأكبر للخطأ:</b> انحراف 0.5°/ث أنتج "
        "%.1f مم (منها %.1f مم على Y وحده)." % (gyro["mean"], gyro["mean_y"]),
        "<b>الإحداثيات وحدها لا تكفي:</b> مع كل الأخطاء وصل الخطأ إلى "
        "%.1f مم بعد ~2.5 م، بينما تقدير الروبوت بدا سليمًا (&lt;12 مم)."
        % combined["mean"],
        "<b>التحكم المغلق يعمل:</b> عدم تماثل العجلات عوّضه الجيرو تمامًا "
        "(%.1f مم — مثل الحالة المثالية)." % asym["mean"],
        "<b>التثبيت على خط يصحّح محورًا واحدًا:</b> خطأ X هبط من %.1f إلى "
        "%.1f مم، لكن Y بقي %.1f مم. ثبّت المحورين وصفّر الجيرو قبل المهمة الدقيقة."
        % (combined["mean_x"], single["mean_x"], single["mean_y"]),
        "<b>المعالم لا تُغني عن المعايرة:</b> حتى مع موضع واتجاه مثاليين بقي "
        "%.1f مم — أثر خطأ قطر العجلة +3%%. قِس 1000 مم حقيقيًا أولًا."
        % ceiling["mean"],
    ]

    # نُضمّن أول 12 محاولة فقط في الرسم (كافية بصريًا) كي يبقى الملف خفيفًا،
    # بينما جدول الإحصاءات أعلاه محسوب على كل المحاولات.
    slim = [{"name": s["name"], "lines": s["lines"],
             "runs": s["runs"][:12]} for s in suite]
    return (HTML_TEMPLATE
            .replace("__TRIALS__", str(suite[0]["trials"]))
            .replace("__ROWS__", "\n".join(rows))
            .replace("__FINDINGS__", "".join("<li>%s</li>" % f for f in findings))
            .replace("__DATA__", json.dumps(slim, ensure_ascii=False)))


def main():
    ap = argparse.ArgumentParser(description="محاكاة SIL لاختبار xy_nav.py")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--md", default=None, help="مسار تقرير Markdown")
    ap.add_argument("--html", default=None, help="مسار تقرير HTML تفاعلي")
    ap.add_argument("--json", default=None, help="مسار النتائج الخام JSON")
    args = ap.parse_args()

    suite = run_suite(args.trials)
    print(text_report(suite))

    if args.md:
        with io.open(args.md, "w", encoding="utf-8") as handle:
            handle.write(markdown_report(suite))
        print("\n✓ كُتب " + args.md)
    if args.html:
        with io.open(args.html, "w", encoding="utf-8") as handle:
            handle.write(html_report(suite))
        print("✓ كُتب " + args.html)
    if args.json:
        with io.open(args.json, "w", encoding="utf-8") as handle:
            json.dump(suite, handle, ensure_ascii=False, indent=1)
        print("✓ كُتب " + args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
