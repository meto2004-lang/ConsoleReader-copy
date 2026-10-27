# -*- coding: utf-8 -*-
"""اختبارات اتساق تمنع عودة الأخطاء التي رُصدت في تحليل 2026-10-27.

هذه اختبارات ثابتة (تقرأ الملفات) — لا تحتاج هاردوير ولا stubs.
هدفها: أي انحراف بين التطبيق والـ Hub والتوثيق يفشل في CI فورًا.
"""

import io
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as handle:
        return handle.read()


def norm(value):
    """قيمة ثابت: أزل المسافات/الاقتباسات وقارن الأرقام رقميًا."""
    v = str(value).strip().strip('"').strip("'").strip()
    try:
        return float(v)
    except ValueError:
        return v


class ConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read("app/index.html")
        cls.hub = read("as3_app.py")
        cls.readme = read("README.md")
        cls.sw = read("app/sw.js")
        cls.ci = read(".github/workflows/tests.yml")

    def hub_version(self):
        m = re.search(r'^HUB_VERSION\s*=\s*"(\d+)"', self.hub, re.M)
        self.assertIsNotNone(m, "لا يوجد HUB_VERSION في as3_app.py")
        return int(m.group(1))

    # --- P1-2: مصدر واحد للإصدار -----------------------------------------
    def test_hub_version_matches_ui_constant(self):
        m = re.search(r"const HUB_VERSION_EXPECTED\s*=\s*(\d+);", self.html)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), self.hub_version())

    def test_no_stale_v6_or_v7_in_ui(self):
        self.assertNotIn("v6", self.html)
        self.assertNotIn("v7", self.html)

    def test_all_version_labels_in_ui_match_expected(self):
        labels = set(re.findall(r"v\d+", self.html))
        self.assertTrue(labels, "لا توجد أي تسمية إصدار في الواجهة")
        self.assertEqual(labels, {"v%d" % self.hub_version()})

    def test_no_stale_v6_in_docs_and_hub(self):
        for rel, text in (("README.md", self.readme), ("as3_app.py", self.hub),
                          ("tests/ui_smoke.mjs", read("tests/ui_smoke.mjs")),
                          ("tests/test_hub.py", read("tests/test_hub.py"))):
            self.assertNotIn("v6", text, "ما زال هناك v6 في " + rel)

    # --- P1-1: فحص الكود يُستدعى قبل الإرسال ------------------------------
    def test_check_program_is_called_before_send(self):
        start = self.html.index("async function sendProgramToRobot")
        end = self.html.index("// تحويل سطور القياس", start)
        body = self.html[start:end]
        self.assertIn("checkProgram(p)", body)
        self.assertIn("if (!check.ok)", body)
        self.assertGreaterEqual(self.html.count("checkProgram("), 2)

    # --- P1-5: سباق pingHub ------------------------------------------------
    def test_ping_hub_passes_from_seq(self):
        start = self.html.index("async function pingHub")
        end = self.html.index("let writeChain", start)
        body = self.html[start:end]
        self.assertRegex(body, r"waitForLine\(/# ✓ HUB_ALIVE/,\s*1500,\s*from\)")

    # --- P1-4: ثوابت الكود اللحظي + مساعد align_on_line -------------------
    def hub_cfg(self):
        m = re.search(r"const HUB_CFG = \{(.*?)\};", self.html, re.S)
        self.assertIsNotNone(m, "لا يوجد HUB_CFG في التطبيق")
        return {k: norm(v) for k, v in
                re.findall(r"(\w+):\s*([^,\n]+)", m.group(1))}

    def python_const(self, name):
        m = re.search(r"^%s\s*=\s*([^#\n]+)" % name, self.hub, re.M)
        self.assertIsNotNone(m, "لا يوجد %s في as3_app.py" % name)
        return norm(m.group(1))

    def test_hub_cfg_matches_python_constants(self):
        cfg = self.hub_cfg()
        pairs = {
            "wheelDiameter": "WHEEL_DIAMETER", "axleTrack": "AXLE_TRACK",
            "straightAccel": "MOVE_ACCEL", "turnAccel": "MOVE_TURN_ACCEL",
            "followGain": "FOLLOW_GAIN", "followSide": "FOLLOW_SIDE",
            "alignSpeed": "ALIGN_SPEED",
        }
        for js_name, py_name in pairs.items():
            self.assertIn(js_name, cfg)
            self.assertEqual(cfg[js_name], self.python_const(py_name),
                             "%s != %s" % (js_name, py_name))

    def test_helper_speed_defaults_match_hub_cfg(self):
        cfg = self.hub_cfg()
        self.assertIn('def find_line(direction=1, max_dist=250, speed=%d):'
                      % cfg["findSpeed"], self.hub)
        self.assertIn('def follow_line(dist, side="L", speed=%d):'
                      % cfg["followSpeed"], self.hub)
        self.assertIn("LINE_THRESHOLD = %d  # عتاة الخط" % cfg["defaultThreshold"],
                      self.hub)

    def test_live_program_defines_align_and_no_hardcoded_45(self):
        self.assertIn('"def align_on_line(speed=" + HUB_CFG.alignSpeed', self.html)
        self.assertIn('"LINE_THRESHOLD = " + th', self.html)
        self.assertNotIn('"LINE_THRESHOLD = 45"', self.html)
        self.assertIn("liveLineThreshold", self.html)

    # --- P2: تنظيف الكود الميت -------------------------------------------
    def test_dead_library_functions_removed(self):
        for name in ("libNormalize", "libUpsert", "libRemove",
                     "parseHubList", "pyFileName", "LIB_MAX",
                     "PROG_NAME_MAX", "codeEditor", "btnEditorSend"):
            self.assertNotIn(name, self.html, "ما زال موجودًا: " + name)
        webtest = read("tests/web.test.mjs")
        for name in ("libUpsert", "libNormalize", "parseHubList", "pyFileName"):
            self.assertNotIn(name, webtest)

    def test_esc_html_is_used(self):
        self.assertGreaterEqual(self.html.count("escHtml("), 2)

    # --- P2-3: تزامن الثوابت ---------------------------------------------
    def test_no_duplicate_move_accel_in_hub(self):
        self.assertEqual(len(re.findall(r"^MOVE_ACCEL\s*=", self.hub, re.M)), 1)
        self.assertEqual(len(re.findall(r"^MOVE_TURN_ACCEL\s*=", self.hub, re.M)), 1)

    def test_check_sync_covers_constants(self):
        tool = read("tools/check_sync.py")
        self.assertIn("SHARED_CONSTANTS", tool)
        self.assertIn("WHEEL_DIAMETER", tool)

    # --- P2-4: Service Worker --------------------------------------------
    def test_sw_uses_stable_key_for_hub_script(self):
        self.assertIn("PY_URL", self.sw)
        self.assertIn("as3_app.py?v=", self.sw)
        self.assertIn("c.put(cachedKey, copy)", self.sw)

    # --- P2-5: CI ---------------------------------------------------------
    def test_ci_compiles_new_files(self):
        for name in ("xy_nav.py", "tools/xy_math.py", "tools/xy_to_commands.py",
                     "tools/xy_sim.py", "tools/xy_calibrate.py"):
            self.assertIn(name, self.ci)

    def test_xy_nav_has_line_snap_guards(self):
        nav = read("xy_nav.py")
        self.assertIn("LINE_TIMEOUT_MS", nav)
        self.assertIn("SNAP_MAX_CORRECTION", nav)
        self.assertIn("_map_problems", nav)


if __name__ == "__main__":
    unittest.main()
