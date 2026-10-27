# -*- coding: utf-8 -*-
"""اختبارات تشغيلية (Software-in-the-Loop) لملف ``xy_nav.py`` الحقيقي.

بعكس ``test_xy_nav.py`` (رياضيات + محاكاة بسيطة)، هذه الاختبارات تُنفّذ الملف
فوق عتاد وهمي يُدخل انزلاقًا وانحراف جيرو وضجيج حساسات، وتتحقق من:

  * أن ``goto()`` يصل فعلًا في الظروف المثالية،
  * أن ``find_line_and_snap()`` لا تتعلّق عند تعطّل الحركة،
  * أنها ترفض التثبيت على خط خاطئ عند تقاطع الخطوط،
  * أن ``run()`` ترفض خريطة ناقصة وتُكمل مهمة كاملة بخريطة صالحة،
  * أن التصحيح بالخطوط يُحسّن المحور الذي يصحّحه فعلًا.

التشغيل:  python -m unittest discover -s tests -t tests -p test_xy_nav_sim.py -v
"""

import contextlib
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import xy_sim as sil  # noqa: E402


def fill_map(m):
    """املأ خريطة صالحة بإحداثيات داخل حدود السجادة."""
    m.FIELD_MAP.update({
        "visitor_pickup": (250, 0),
        "green_area": (400, 200),
        "museum_area": (600, 200),
        "line_approach": (500, 400),
        "line_y": 400,
        "tower_pickup": (700, 300),
        "tower_target": (850, 300),
        "cobblestone": (1000, 0),
    })
    m.ARTIFACT_SLOTS[:] = [(1100, 100), (1100, 200),
                           (1100, 300), (1100, 400)]
    for key, y in (("red", 100), ("green", 200), ("black", 300),
                   ("blue", 400), ("yellow", 500)):
        m.MUSEUM_SPOTS[key] = (1300, y)
    m.SWEEP_PATH[:] = [(1500, 0), (1700, 0), (1900, 0)]


class IdealMissionTests(unittest.TestCase):
    def test_ideal_mission_reaches_every_waypoint(self):
        r = sil.run_mission(0, {})
        self.assertTrue(r["ok"], "فشل الوصول في الظروف المثالية: %s" % r["legs"])
        self.assertEqual(len(r["legs"]), len(sil.WAYPOINTS))
        self.assertLess(r["final_true_err"], 25.0)

    def test_wheel_asymmetry_is_corrected_by_closed_loop(self):
        r = sil.run_mission(0, dict(sil.SCENARIOS[4][1]))
        self.assertTrue(r["ok"])
        self.assertLess(r["final_true_err"], 25.0,
                        "المتحكم يجب أن يعوّض عدم تماثل العجلات بالجيرو")

    def test_gyro_drift_is_the_dominant_error_source(self):
        gyro = sil.run_mission(0, dict(sil.SCENARIOS[3][1]))
        calib = sil.run_mission(0, dict(sil.SCENARIOS[1][1]))
        self.assertGreater(gyro["final_true_err"], calib["final_true_err"] * 1.8)
        self.assertGreater(gyro["final_y_err"], 80.0)

    def test_combined_errors_exceed_useful_precision(self):
        """توثيق الحدّ: الإحداثيات وحدها لا تكفي لوضع دقيق."""
        r = sil.run_mission(0, dict(sil.COMBINED))
        self.assertTrue(r["ok"], "goto يعتبر نفسه ناجحًا رغم الخطأ الحقيقي")
        self.assertGreater(r["final_true_err"], 100.0)
        self.assertLess(r["final_est_err"], 20.0,
                        "تقدير الروبوت يبدو ممتازًا بينما موقعه الحقيقي بعيد")


class LineSnapRegressionTests(unittest.TestCase):
    def test_stalled_robot_does_not_hang(self):
        """كانت الحلقة لا نهائية: عدّاد المسافة لا يتغيّر عند تعطّل الحركة."""
        sim = sil.Sim(seed=3, stall=True, lines=[("v", 900, 20)])
        m = sil.load_xy_nav(sim)
        nav = sil.new_nav(m, sim)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = nav.find_line_and_snap("x", 900, max_dist=200)
        self.assertFalse(result)
        self.assertIn("مهلة", buf.getvalue())
        self.assertLess(sim.steps, 400, "يجب أن يتوقف خلال ~2.5 ثانية محاكاة")
        self.assertEqual(nav.x, 0.0, "لا تثبيت عند الفشل")

    def test_crossing_line_false_snap_is_rejected(self):
        """الوقوف على خط أفقي كان يثبّت X على بُعد 200 مم من المكان الحقيقي."""
        sim = sil.Sim(seed=3, lines=sil.LINES)
        m = sil.load_xy_nav(sim)
        nav = sil.new_nav(m, sim)
        nav.x, nav.y = 700.0, 400.0
        sim.x, sim.y = 700.0, 400.0
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = nav.find_line_and_snap("x", 900, max_dist=250)
        self.assertFalse(result)
        self.assertIn("رُفض تثبيت", buf.getvalue())
        self.assertEqual(nav.x, 700.0)

    def test_valid_snap_corrects_its_axis(self):
        """تصحيح ضمن الحدّ المقبول يُقبل ويُلغي انحراف التقدير."""
        sim = sil.Sim(seed=3, lines=[("v", 1400, 20)])
        m = sil.load_xy_nav(sim)
        nav = sil.new_nav(m, sim)
        nav.x = 1360.0
        sim.x = 1390.0
        sim.y = nav.y = 0.0
        self.assertTrue(nav.find_line_and_snap("x", 1390, max_dist=250))
        self.assertEqual(nav.x, 1390.0)

    def test_line_snap_improves_x_error_in_full_mission(self):
        combined = sil.run_mission(0, dict(sil.COMBINED))
        snapped = sil.run_mission(0, dict(sil.SCENARIOS[6][1]))
        self.assertTrue(snapped["snapped"])
        self.assertLess(snapped["final_x_err"], combined["final_x_err"] * 0.4,
                        "التثبيت يجب أن يقلّل خطأ المحور X بوضوح")
        self.assertGreater(snapped["final_y_err"], 60.0,
                           "لكنه لا يصحّح Y — انحراف الجيرو ما زال موجودًا")

    def test_perfect_landmarks_still_need_odometry_calibration(self):
        """حتى مع موضع/اتجاه مثاليين، خطأ معايرة العجلة يترك أثرًا."""
        perfect = sil.run_mission(0, dict(sil.SCENARIOS[8][1]))
        self.assertLess(perfect["final_true_err"], 60.0)
        self.assertGreater(perfect["final_true_err"], 20.0,
                           "خطأ قطر العجلة +3% لا يُصلحه أي معلم لوني")


class CalibrationScriptTests(unittest.TestCase):
    def test_calibration_program_runs_and_prints_summary(self):
        """برنامج المعايرة يُنفَّذ كاملًا فوق الـ stubs (بلا هاردوير).

        نستبدل انتظار الزر بوظيفة فارغة، فتبقى كل استدعاءات Pybricks
        (reset_heading / straight / turn / reflection / beep) تحت الاختبار.
        """
        path = os.path.join(ROOT, "tools", "xy_calibrate.py")
        with io.open(path, encoding="utf-8") as handle:
            src = handle.read()
        head = src[:src.index("def main():")]
        main_src = src[src.index("def main():"):src.rindex("main()")]
        ns = {"__name__": "xy_calibrate_under_test"}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(compile(head + main_src, path, "exec"), ns)
            ns["press_left"] = lambda label: None
            ns["main"]()
        out = buf.getvalue()
        self.assertIn("# CALIB", out)
        self.assertIn("LINE_THRESHOLD", out)
        self.assertIn("انحراف الجيرو", out)
        self.assertIn("جدول تصحيح قطر العجلة", out)


class RunProgramTests(unittest.TestCase):
    def test_run_refuses_incomplete_map(self):
        sim = sil.Sim(seed=0, lines=sil.LINES)
        m = sil.load_xy_nav(sim)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.run()
        out = buf.getvalue()
        self.assertIn("FIELD_MAP غير مكتمل", out)
        self.assertIn("line_y", out)
        self.assertEqual(sim.light_color, None)
        self.assertGreater(len(sim.beeps), 0)

    def test_run_rejects_bad_value_types(self):
        sim = sil.Sim(seed=0, lines=sil.LINES)
        m = sil.load_xy_nav(sim)
        fill_map(m)
        m.FIELD_MAP["line_y"] = (400, 400)   # tuple بدل رقم
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.run()
        self.assertIn("line_y", buf.getvalue())
        self.assertEqual(sim.light_color, None)

    def test_run_completes_full_mission_with_valid_map(self):
        sim = sil.Sim(seed=0, lines=sil.LINES,
                      color_fn=lambda s: m.Color.RED)
        m = sil.load_xy_nav(sim)
        fill_map(m)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.run()
        out = buf.getvalue()
        self.assertIn("# FINAL", out, "المهمة لم تكتمل: %s" % out[-500:])
        self.assertNotIn("فشل التنقّل", out)
        self.assertEqual(sim.light_color, m.Color.BLUE)
        self.assertGreater(len(sim.arm_calls), 0)
        self.assertLess(sim.steps, sil.Sim.MAX_STEPS)


if __name__ == "__main__":
    unittest.main()
