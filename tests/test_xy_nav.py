# -*- coding: utf-8 -*-
"""اختبارات طبقة الملاحة (x, y) — رياضيات + محاكاة حركة الروبوت.

تشغيل:  python -m unittest discover -s tests -t tests -v
"""

import os
import subprocess
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
STUBS = os.path.join(ROOT, "tests", "stubs")
for path in (TOOLS, STUBS):
    if path not in sys.path:
        sys.path.insert(0, path)

import xy_math  # noqa: E402
import hubclock  # noqa: E402


def load_xy_nav():
    """نفّذ xy_nav.py قبل البرنامج الرئيسي (لا نشغّل run() في الاختبارات)."""
    hubclock.reset_clock()
    path = os.path.join(ROOT, "xy_nav.py")
    with open(path, encoding="utf-8") as handle:
        src = handle.read()
    marker = "# ==== 8) البرنامج الرئيسي"
    head = src[:src.index(marker)]
    module = types.ModuleType("xy_nav_under_test")
    module.__dict__["__name__"] = "xy_nav_under_test"
    exec(compile(head, path, "exec"), module.__dict__)
    return module


class SimDrive:
    """محرك وهمي يدمج السرعة والدوران على خطوات 10ms (مثل wait(10))."""

    DT = 0.010

    def __init__(self, imu):
        self.imu = imu
        self.d = 0.0
        self.stopped = 0

    def distance(self):
        return self.d

    def drive(self, speed, turn_rate):
        self.d += speed * self.DT
        self.imu.heading_value = xy_math.wrap180(
            self.imu.heading_value + turn_rate * self.DT)

    def stop(self):
        self.stopped += 1

    def reset(self):
        self.d = 0.0

    def use_gyro(self, *args):
        pass

    def settings(self, **kwargs):
        pass


class MathTests(unittest.TestCase):
    def test_wrap180(self):
        self.assertAlmostEqual(xy_math.wrap180(370), 10)
        self.assertAlmostEqual(xy_math.wrap180(-190), 170)
        self.assertAlmostEqual(xy_math.wrap180(180), -180)
        self.assertAlmostEqual(xy_math.wrap180(0), 0)

    def test_bearing_uses_clockwise_positive(self):
        self.assertAlmostEqual(xy_math.bearing(0, 0, 100, 0), 0)
        self.assertAlmostEqual(xy_math.bearing(0, 0, 0, 100), 90)
        self.assertAlmostEqual(xy_math.bearing(0, 0, -100, 0), -180)
        self.assertAlmostEqual(xy_math.bearing(0, 0, 0, -100), -90)

    def test_plan_two_legs(self):
        legs = xy_math.plan([(0, 0), (300, 0), (300, 400)])
        self.assertEqual(legs, [("S", 300.0), ("T", 90.0), ("S", 400.0)])

    def test_plan_final_heading(self):
        legs = xy_math.plan([(100, 0)], final_heading=180)
        self.assertEqual(legs[-1], ("T", -180.0))  # wrap180 يعيد -180 لا +180

    def test_to_commands_and_python(self):
        legs = [("T", 90.0), ("S", 400.0)]
        self.assertEqual(xy_math.to_commands(legs), ["T 90", "S 400"])
        self.assertIn("    robot.turn(90)", xy_math.to_python(legs))
        self.assertIn("    robot.straight(400)", xy_math.to_python(legs))

    def test_empty_plan_is_valid_python(self):
        self.assertIn("    pass", xy_math.to_python([]))


class NavTests(unittest.TestCase):
    def setUp(self):
        self.m = load_xy_nav()
        self.sim = SimDrive(self.m.hub.imu)
        self.m.robot = self.sim

    def test_goto_reaches_target(self):
        nav = self.m.Nav()
        ok = nav.goto(300, 400)
        self.assertTrue(ok, "المهلة انتهت قبل الوصول؛ الموقع: %s" % str(nav.where()))
        self.assertLess(abs(nav.x - 300), 25)
        self.assertLess(abs(nav.y - 400), 25)

    def test_goto_rejects_out_of_field(self):
        nav = self.m.Nav()
        self.assertFalse(nav.goto(99999, 0))
        self.assertEqual(self.sim.d, 0.0)

    def test_face(self):
        nav = self.m.Nav()
        self.assertTrue(nav.face(90))
        self.assertAlmostEqual(nav.heading, 90, delta=3)

    def test_snap_clears_accumulated_error(self):
        nav = self.m.Nav()
        nav.x, nav.y = 55.0, -70.0        # انحراف متراكم متخيّل
        nav.snap("x", 600)
        nav.snap("y", 200)
        self.assertEqual((nav.x, nav.y), (600.0, 200.0))

    def test_find_line_and_snap(self):
        nav = self.m.Nav()
        self.m.line_sensor.reflection = lambda: 5   # خط داكن مباشرة
        # تصحيح صغير (25 مم) ضمن SNAP_MAX_CORRECTION يُقبل
        self.assertTrue(nav.find_line_and_snap("y", 25))
        self.assertEqual(nav.y, 25.0)

    def test_find_line_and_snap_rejects_implausible_correction(self):
        """خط آخر/قراءة خاطئة لا يجوز أن تنقل الروبوت 250 مم دفعة واحدة."""
        nav = self.m.Nav()
        self.m.line_sensor.reflection = lambda: 5
        self.assertFalse(nav.find_line_and_snap("y", 250))
        self.assertEqual(nav.y, 0.0)

    def test_map_problems_names_bad_keys(self):
        m = self.m
        problems = m._map_problems()
        self.assertIn("line_y", problems)
        self.assertIn("ARTIFACT_SLOTS[0]", problems)
        self.assertTrue(problems)

    def test_map_rejects_wrong_types(self):
        m = self.m
        for key in ("visitor_pickup", "green_area", "museum_area",
                    "line_approach", "tower_pickup", "tower_target", "cobblestone"):
            m.FIELD_MAP[key] = (100, 100)
        m.FIELD_MAP["line_y"] = (200, 200)      # خطأ: tuple بدل رقم
        m.ARTIFACT_SLOTS[:] = [(10, 10)] * 4
        for key in m.MUSEUM_SPOTS:
            m.MUSEUM_SPOTS[key] = (200, 200)
        m.SWEEP_PATH[:] = [(300, 300)] * 3
        self.assertIn("line_y", m._map_problems())
        self.assertFalse(m._map_ready())

    def test_read_color_majority_vote(self):
        nav = self.m.Nav()
        seq = iter(["red"] * 5 + ["blue"] * 2)
        self.m.ARTIFACT_SENSOR.color = lambda: next(seq)
        self.assertEqual(nav.read_color(), "red")

    def test_map_not_ready_by_default(self):
        self.assertFalse(self.m._map_ready())

    def test_map_ready_after_filling(self):
        m = self.m
        for key in ("visitor_pickup", "green_area", "museum_area",
                    "line_approach", "tower_pickup", "tower_target", "cobblestone"):
            m.FIELD_MAP[key] = (100, 100)
        m.FIELD_MAP["line_y"] = 250
        m.ARTIFACT_SLOTS[:] = [(10, 10)] * 4
        for key in m.MUSEUM_SPOTS:
            m.MUSEUM_SPOTS[key] = (200, 200)
        m.SWEEP_PATH[:] = [(300, 300)] * 3
        self.assertTrue(m._map_ready())


class CliTests(unittest.TestCase):
    def test_cli_ble_output(self):
        out = subprocess.check_output(
            [sys.executable, os.path.join(TOOLS, "xy_to_commands.py"),
             "0,0", "300,0", "300,400", "--ble"],
            text=True, timeout=30)
        self.assertIn("T 90", out)
        self.assertIn("S 400", out)

    def test_cli_python_output(self):
        out = subprocess.check_output(
            [sys.executable, os.path.join(TOOLS, "xy_to_commands.py"),
             "0,0", "300,0"],
            text=True, timeout=30)
        self.assertIn("def run():", out)
        self.assertIn("robot.straight(300)", out)


if __name__ == "__main__":
    unittest.main()
