"""اختبارات منطق الـ Hub (as3.py / as3_app.py) بلا هاردوير.

التشغيل:
    python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import unittest

import hub_loader
import hubclock


def capture(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args)
    return result, buf.getvalue()


class GeneratedProgramTests(unittest.TestCase):
    """البرنامج الناتج يجب أن يكون Python صالحًا لغويًا (بلا Pybricks)."""

    def _program(self, module, with_sensors=True):
        module.actions.clear()
        module.refl.clear()
        module.refl.add(9)
        module.refl.add(90)
        if with_sensors:
            module.actions.append(("sensor", ["# LEFT sensor (Port.C): reflection=9"], None, None))
        module.actions.append(("move", [("turn", 90), ("straight", 500)], 0, 0))
        module.actions.append(("move", [("turn", -90), ("straight", 200)], 500, 90))
        module.actions.append(("move", [("find_line", (1, 260)), ("align_line", 25)], 700, 0))
        module.actions.append(("move", [("follow_line", (400, "L"))], 800, 0))
        module.actions.append(("move", [("follow_line", (-250, "R"))], 1200, 0))
        out = capture(module.print_full_program)[1]
        if "#@@PROGRAM_BEGIN@@" in out:
            out = out.split("#@@PROGRAM_BEGIN@@")[1].split("#@@PROGRAM_END@@")[0]
        return out

    def _assert_compiles(self, text):
        compile(text, "<generated>", "exec")
        self.assertIn("def run():", text)
        self.assertIn("robot.settings(straight_acceleration=", text)
        self.assertIn('follow_line(-250, "R")', text)  # الإشارة محفوظة (رجوع)

    def test_original_program_compiles(self):
        module = hub_loader.load_original()
        self._assert_compiles(self._program(module))

    def test_app_program_compiles(self):
        module = hub_loader.load_app()
        self._assert_compiles(self._program(module))

    def test_program_without_sensors_compiles(self):
        module = hub_loader.load_app()
        module.actions.clear()
        module.refl.clear()
        module.actions.append(("move", [("straight", 300)], 0, 0))
        text = capture(module.print_full_program)[1]
        text = text.split("#@@PROGRAM_BEGIN@@")[1].split("#@@PROGRAM_END@@")[0]
        compile(text, "<generated>", "exec")
        self.assertNotIn("ColorSensor(Port.C)", text)   # لا نضيف حساسات بلا داعٍ


class SingleSensorTests(unittest.TestCase):
    """النسخة الحالية تعتمد على حسّاس ألوان واحد على المنفذ C."""

    def test_generated_program_uses_one_sensor_only(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.refl.clear()
        m.actions.append(("sensor", ["# LINE sensor (Port.C): reflection=9"], None, None))
        m.actions.append(("move", [("find_line", (1, 250)), ("align_line", 25)], 0, 0))
        m.actions.append(("move", [("follow_line", (300, "L"))], 250, 0))
        text = capture(m.print_full_program)[1]
        text = text.split("#@@PROGRAM_BEGIN@@")[1].split("#@@PROGRAM_END@@")[0]
        compile(text, "<generated>", "exec")
        self.assertIn("line_sensor = ColorSensor(Port.C)", text)
        self.assertNotIn("ColorSensor(Port.D)", text)    # لا حسّاس ثانٍ على D
        self.assertIn("arm_motor   = Motor(Port.D)", text)
        self.assertNotIn("right_sensor", text)
        self.assertEqual(text.count("ColorSensor("), 1)  # تهيئة واحدة فقط
        # كل الدوال المساعدة تقرأ من الحسّاس الوحيد
        self.assertEqual(text.count("line_sensor.reflection()"), 3)

    def test_original_program_uses_one_sensor_only(self):
        m = hub_loader.load_original()
        m.actions.clear()
        m.refl.clear()
        m.actions.append(("move", [("find_line", (1, 250)), ("align_line", 25)], 0, 0))
        text = capture(m.print_full_program)[1]
        self.assertNotIn("ColorSensor(Port.D)", text)
        self.assertIn("arm_motor   = Motor(Port.D)", text)
        self.assertEqual(text.count("ColorSensor("), 1)

    def test_hub_reads_the_line_sensor(self):
        m = hub_loader.load_app()
        self.assertIs(m.line_sensor, m.line_sensor)      # كائن واحد
        self.assertFalse(hasattr(m, "right_sensor"))
        m.line_sensor.reflection_value = 12
        self.assertEqual(m.sample_sensors(True), 12)

    def test_find_stops_when_the_single_sensor_sees_the_line(self):
        m = hub_loader.load_app()
        m.run_th = 40
        m.run_phase = "start"
        m.line_sensor.reflection_value = 10              # على الخط مباشرة
        self.assertFalse(m._run_step_find(1, 250))       # خطوة التهيئة
        self.assertTrue(m._run_step_find(1, 250))        # يكتشف الخط فيتوقف
        self.assertEqual(m.robot.braked, 1)

    def test_find_ignores_bright_surface(self):
        m = hub_loader.load_app()
        m.run_th = 40
        m.run_phase = "start"
        m.line_sensor.reflection_value = 90              # خلفية بيضاء
        self.assertFalse(m._run_step_find(1, 250))
        self.assertFalse(m._run_step_find(1, 250))
        self.assertEqual(m.robot.braked, 0)

    def test_align_is_a_rotation_search(self):
        m = hub_loader.load_app()
        m.run_th = 40
        m.run_phase = "start"
        m.line_sensor.reflection_value = 20              # يرى الخط
        self.assertFalse(m._run_step_align(25))          # تهيئة
        self.assertTrue(m._run_step_align(25))
        m2 = hub_loader.load_app()
        m2.run_th = 40
        m2.run_phase = "start"
        m2.line_sensor.reflection_value = 80             # لا يرى الخط: يستمر بالدوران
        self.assertFalse(m2._run_step_align(25))
        self.assertFalse(m2._run_step_align(25))

    def test_smart_line_point_has_no_useless_align(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.last_distance = 0
        m.last_heading = 0
        m.robot.distance_value = 200
        m.line_sensor.reflection_value = 8               # على الخط الآن
        m.do_find_line_point()
        segs = m.actions[-1][1]
        self.assertEqual([seg[0] for seg in segs], ["find_line"])   # بلا align
        self.assertEqual(segs[0][1], (1, 250))           # 200 + هامش 50

    def test_auto_read_streams_one_sensor_line(self):
        m = hub_loader.load_app()
        m.auto_tick = 0
        m.watch_d = 0
        m.watch_h = 0
        m.robot.distance_value = 120                     # حركة → بثّ
        m.line_sensor.reflection_value = 33
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for _ in range(m.AUTO_SAMPLE_EVERY):   # تُقرأ كل 3 دورات
                m.auto_read_tick()
        line = buf.getvalue().strip()
        self.assertTrue(line.startswith("# T d=120"), line)
        self.assertIn(" C=33", line)
        self.assertNotIn(" R=", line)                    # لا حسّاس ثانٍ


class ThresholdTests(unittest.TestCase):
    """عتبة الخط تُحسب من العدّادين بدل قائمة العينات (توفير ذاكرة)."""

    def test_needs_a_clear_gap(self):
        module = hub_loader.load_app()
        module.refl.clear()
        for v in (80, 85, 82):
            module.refl.add(v)
        self.assertIsNone(module.estimated_threshold())

    def test_midpoint_of_min_and_max(self):
        module = hub_loader.load_app()
        module.refl.clear()
        for v in (88, 12, 90, 9, 70):
            module.refl.add(v)
        self.assertEqual(module.refl.lo, 9)
        self.assertEqual(module.refl.hi, 90)
        self.assertEqual(module.estimated_threshold(), 49)

    def test_collects_only_when_moving(self):
        module = hub_loader.load_app()
        module.refl.clear()
        module.sample_sensors(False)      # سكون: لا تُحسب
        self.assertEqual(module.refl.n, 0)
        module.sample_sensors(True)       # حركة: تُحسب
        self.assertEqual(module.refl.n, 1)


class CodeReceiveTests(unittest.TestCase):
    """آلة استلام الكود K … E: الحالات الحدّية التي كانت تُعلّق الـ Hub."""

    LINES = ["T -90", "S 500", "F 1 250", "A 25", "L 400 L", "L 300 R", "S -120"]

    def _wire(self, lines):
        return "K" + "".join(line + "\n" for line in lines) + "E"

    def test_roundtrip(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, self._wire(self.LINES))
        self.assertFalse(m.code_mode)
        self.assertEqual([seg[0] for seg in m.run_queue],
                         ["turn", "straight", "find_line", "align_line",
                          "follow_line", "follow_line", "straight"])
        self.assertEqual(m.run_queue[0], ("turn", -90))
        self.assertEqual(m.run_queue[5], ("follow_line", 300, "R"))
        self.assertEqual(m.code_skipped, 0)

    def test_e_finishes_even_mid_line(self):
        # كان E يُقبل فقط في بداية سطر؛ لو ضاع \n يبقى الهاب عالقًا للأبد
        m = hub_loader.load_app()
        hub_loader.feed(m, "K" + "T 90\n" + "S 400" + "E")
        self.assertFalse(m.code_mode)
        self.assertEqual(m.run_queue, [("turn", 90), ("straight", 400)])

    def test_long_line_is_dropped_not_truncated(self):
        # قصّ "S 4000" إلى "S 400" ينفّذ أمرًا خاطئًا — يجب تجاهل السطر كله
        m = hub_loader.load_app()
        long_line = "S " + "1" * 40
        hub_loader.feed(m, self._wire(["T 45", long_line, "S 250"]))
        self.assertEqual(m.run_queue, [("turn", 45), ("straight", 250)])
        self.assertEqual(m.code_skipped, 1)

    def test_duplicate_e_is_harmless(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, "KT 30\nEE")
        self.assertFalse(m.code_mode)
        self.assertEqual(m.run_queue, [("turn", 30)])

    def test_timeout_leaves_previous_code_untouched(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 111)]
        hub_loader.feed(m, "KT 30\n")
        self.assertTrue(m.code_mode)
        hubclock.advance(m.CODE_TIMEOUT_MS + 1)
        # نفس الفحص الموجود في الحلقة الرئيسية
        if m.code_mode and m.code_watch.time() > m.CODE_TIMEOUT_MS:
            m.code_receive_abort("مهلة")
        self.assertFalse(m.code_mode)
        self.assertEqual(m.run_queue, [("straight", 111)])

    def test_empty_submission_keeps_previous_code(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 222)]
        hub_loader.feed(m, "KE")
        self.assertEqual(m.run_queue, [("straight", 222)])

    def test_threshold_command_sets_run_threshold(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, "H 57\n")
        self.assertEqual(m.run_th, 57)
        # H أمر سطر واحد: يجب أن يعود الـ Hub جاهزًا، وإلا ابتلع G التالي
        self.assertFalse(m.code_mode)
        hub_loader.feed(m, "H 999\n")
        self.assertEqual(m.run_th, m.TH_MAX)     # يُقصّ إلى النطاق الآمن

    def test_threshold_then_go_starts_run(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, "KT 30\nE")
        m.run_queue = [("turn", 30)]
        hub_loader.feed(m, "H 61\nG")
        self.assertTrue(m.run_active)
        self.assertEqual(m.run_th, 61)

    def test_threshold_survives_start(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, "H 57\n")
        m.run_queue = [("straight", 100)]
        m.run_active = False
        _, out = capture(m.run_start)
        self.assertEqual(m.run_th, 57)          # لا تُستبدل بالمحسوبة في G
        self.assertIn("عتاة الخط = 57", out)
        self.assertTrue(m.run_active)

    def test_run_limit_guards_memory(self):
        m = hub_loader.load_app()
        lines = ["S 10"] * (m.RUN_MAX_LINES + 5)
        hub_loader.feed(m, self._wire(lines))
        self.assertEqual(len(m.run_queue), m.RUN_MAX_LINES)
        self.assertEqual(m.code_skipped, 5)


class BulkReceiveTests(unittest.TestCase):
    """الوضع السريع: B + حزم N (بايتان طول + حمولة) + E.

    التطبيق يرسل البرنامج كاملًا في 10–20 حزمة بدل ~900 كتابة حرف واحد،
    والأسطر قد تنقسم بين حزمتين — لهذا تُختبر هنا حدود الحزم.
    """

    PAYLOAD = "T -90\nS 500\nF 1 250\nA 25\nL 400 L\nS -120\n"

    def _frames(self, text, size):
        out = "B"
        for i in range(0, len(text), size):
            chunk = text[i:i + size]
            out += "N" + chr(len(chunk) & 0xFF) + chr(len(chunk) >> 8) + chunk
        return out + "E"

    def _run(self, size):
        m = hub_loader.load_app()
        hub_loader.feed(m, self._frames(self.PAYLOAD, size))
        return m

    def test_split_frames_anywhere(self):
        for size in (1, 5, 13, 90):
            with self.subTest(size=size):
                m = self._run(size)
                self.assertFalse(m.code_mode)
                self.assertEqual(
                    [seg[0] for seg in m.run_queue],
                    ["turn", "straight", "find_line", "align_line",
                     "follow_line", "straight"],
                )
                self.assertEqual(m.code_skipped, 0)

    def test_oversized_frame_aborts(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 77)]
        big = m.FRAME_MAX + 1
        hub_loader.feed(m, "BN" + chr(big & 0xFF) + chr(big >> 8))
        self.assertFalse(m.code_mode)
        self.assertEqual(m.run_queue, [("straight", 77)])

    def test_bulk_then_legacy_still_works(self):
        m = hub_loader.load_app()
        frame = "T 15\n"
        hub_loader.feed(m, "B" + "N" + chr(len(frame)) + chr(0) + frame + "E")
        self.assertEqual(m.run_queue, [("turn", 15)])
        hub_loader.feed(m, "KS 20\nE")
        self.assertEqual(m.run_queue, [("straight", 20)])


class ProgramStoreTests(unittest.TestCase):
    """مكتبة برامج على الـ Hub (v9): W حفظ · V عرض · J تشغيل · D حذف."""

    FRAME = "T 90\nS 300\nF 1 250\n"

    def _hub(self, text=None):
        m = hub_loader.load_app()
        frame = text if text is not None else self.FRAME
        hub_loader.feed(m, "B" + "N" + chr(len(frame) & 0xFF) + chr(len(frame) >> 8) + frame + "E")
        return m

    def test_save_then_list(self):
        m = self._hub()
        _, out = capture(hub_loader.feed, m, "W خط أول\n")
        self.assertIn("حُفظ على الهاب", out)
        self.assertEqual(len(m.programs), 1)
        self.assertEqual(m.programs[0][0], "خط أول")
        _, out2 = capture(hub_loader.feed, m, "V")
        self.assertIn("# V 1", out2)
        self.assertIn("# P 0 3 خط أول", out2)
        self.assertTrue(out2.rstrip().endswith("# V end"))

    def test_saved_program_runs_by_number(self):
        m = self._hub()
        hub_loader.feed(m, "W مسار\n")
        m.run_queue = []                       # كأن الـ Hub أُعيد تشغيله بعد الحفظ
        _, out = capture(hub_loader.feed, m, "J 0\n")
        self.assertTrue(m.run_active)
        self.assertEqual([seg[0] for seg in m.run_queue],
                         ["turn", "straight", "find_line"])
        self.assertIn("برنامج محفوظ: مسار", out)

    def test_delete_removes_program(self):
        m = self._hub()
        hub_loader.feed(m, "W أ\n")
        m.run_queue = [("turn", 5)]
        hub_loader.feed(m, "W ب\n")
        _, out = capture(hub_loader.feed, m, "D 0\n")
        self.assertEqual([p[0] for p in m.programs], ["ب"])
        self.assertIn("حُذف من الهاب", out)

    def test_limit_is_explained_not_silent(self):
        m = self._hub()
        for i in range(m.MAX_PROGRAMS):
            hub_loader.feed(m, "W ب" + str(i) + "\n")
        self.assertEqual(len(m.programs), m.MAX_PROGRAMS)
        _, out = capture(hub_loader.feed, m, "W زائد\n")
        self.assertIn("امتلأت ذاكرة", out)
        self.assertEqual(len(m.programs), m.MAX_PROGRAMS)

    def test_same_name_replaces(self):
        m = self._hub()
        hub_loader.feed(m, "W مكرر\n")
        m.run_queue = [("straight", 50)]
        hub_loader.feed(m, "W مكرر\n")
        self.assertEqual(len(m.programs), 1)
        self.assertEqual(m.programs[0][1], [("straight", 50)])

    def test_invalid_index_does_not_crash_or_run(self):
        m = self._hub()
        for cmd in ("J 0\n", "J -1\n", "J abc\n", "D 9\n"):
            with self.subTest(cmd=cmd):
                _, out = capture(hub_loader.feed, m, cmd)
                self.assertIn("⚠", out)
                self.assertFalse(m.run_active)
        self.assertEqual(m.programs, [])

    def test_save_without_program_warns(self):
        m = hub_loader.load_app()
        m.run_queue = []
        m.code_new = []
        _, out = capture(hub_loader.feed, m, "W لا شيء\n")
        self.assertIn("لا يوجد برنامج لحفظه", out)
        self.assertEqual(m.programs, [])

    def test_long_name_is_truncated_not_leaked_into_commands(self):
        m = self._hub()
        hub_loader.feed(m, "W " + "ا" * 40 + "\n")
        self.assertEqual(len(m.programs), 1)
        self.assertLessEqual(len(m.programs[0][0]), m.PROG_NAME_MAX)
        # الـ Hub عاد جاهزًا: أمر عادي بعد الاسم يُنفَّذ
        hub_loader.feed(m, "V")
        self.assertFalse(m.code_mode)


class AppCommandRoutingTests(unittest.TestCase):
    """كل حرف يرسله التطبيق يجب أن يصل إلى وظيفته على الـ Hub.

    الحروف R/L/F/T/U/C (أزرار التدريب) و w/s/a/d (التحكم عن بعد) كانت
    تُرسَل من التطبيق ولا يجدها الـ Hub — عطل صامت لا يظهر في أي اختبار
    لأن الاختبارات كانت تنادي دوال do_* مباشرة. هذه المجموعة تمرّر الحرف
    عبر ``handle_app_command`` نفسه كما يفعل stdin.
    """

    def _hub(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.refl.clear()
        return m

    def _called(self, m, ch):
        seen = []
        for name in ("do_record_move", "do_read_sensors", "do_print_program",
                     "do_find_line_point", "do_follow_line_seg", "do_undo"):
            original = getattr(m, name)
            def spy(*a, _n=name, _o=original, **k):
                seen.append(_n)
                return _o(*a, **k)
            setattr(m, name, spy)
        hub_loader.feed(m, ch)
        return seen

    def test_training_letters_reach_their_handlers(self):
        expected = {
            "R": "do_record_move",
            "L": "do_read_sensors",
            "C": "do_print_program",
            "F": "do_find_line_point",
            "T": "do_follow_line_seg",
            "U": "do_undo",
        }
        for ch, fn in expected.items():
            with self.subTest(cmd=ch):
                m = self._hub()
                self.assertEqual(self._called(m, ch), [fn])

    def test_each_training_letter_is_ignored_when_unknown(self):
        # الحروف غير المعروفة لا تنفّذ أي شيء ولا تُنتج أثرًا
        m = self._hub()
        self.assertEqual(self._called(m, "Z"), [])
        self.assertEqual(m.actions, [])

    def test_remote_letters_map_to_drive(self):
        cases = {"w": (1, 0), "s": (-1, 0), "a": (0, -1), "d": (0, 1)}
        for ch, (sgn_speed, sgn_turn) in cases.items():
            with self.subTest(cmd=ch):
                m = self._hub()
                hub_loader.feed(m, ch)
                self.assertTrue(m.rc_driving, "لم يبدأ الدفع عن بعد")
                self.assertEqual(m.rc_target_speed, sgn_speed * m.RC_SPEED)
                self.assertEqual(m.rc_target_turn, sgn_turn * m.RC_TURN)

    def test_x_stops_and_releases_motors(self):
        m = self._hub()
        hub_loader.feed(m, "w")
        self.assertTrue(m.rc_driving)
        hub_loader.feed(m, "x")
        # x = إيقاف ناعم: يُصفّر الهدف فورًا، ثم تُحرَّر المحركات في الدورات التالية
        self.assertEqual(m.rc_target_speed, 0)
        self.assertEqual(m.rc_target_turn, 0)
        for _ in range(4):
            m.rc_tick()
        self.assertFalse(m.rc_driving, "لم تُحرَّر المحركات بعد الإيقاف")

    def test_training_command_halts_remote_driving_first(self):
        m = self._hub()
        hub_loader.feed(m, "w")
        self.assertTrue(m.rc_driving)
        self._called(m, "R")
        self.assertFalse(m.rc_driving, "لم يتوقف الدفع قبل التسجيل")

    def test_ping_answers_with_version_and_memory(self):
        m = self._hub()
        _, out = capture(hub_loader.feed, m, "?")
        self.assertIn("# ✓ HUB_ALIVE v" + m.HUB_VERSION, out)
        self.assertRegex(out.strip(), r"^# ✓ HUB_ALIVE v\d+ \d+ \d+$")

    def test_auto_read_letters_toggle_stream(self):
        m = self._hub()
        hub_loader.feed(m, "y")
        self.assertTrue(m.AUTO_STREAM)
        hub_loader.feed(m, "z")
        self.assertFalse(m.AUTO_STREAM)

    def test_letters_not_swallowed_during_code_receive(self):
        # أثناء استلام الكود تُعالَج الحروف كبيانات، وبعد E يعود التدريب
        m = self._hub()
        hub_loader.feed(m, "K")
        self.assertTrue(m.code_mode)
        hub_loader.feed(m, "S 10\nE")
        self.assertFalse(m.code_mode)
        self.assertEqual(self._called(m, "R"), ["do_record_move"])


class RecordingTests(unittest.TestCase):
    def test_action_limit_keeps_tracking_point(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.MAX_ACTIONS = 2
        for _ in range(3):
            m.push_action("move", [("straight", 100)], 0, 0)
        self.assertEqual(len(m.actions), 2)

    def test_follow_line_keeps_backwards_sign(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.last_distance = 500
        m.robot.distance_value = 300          # رجع 200 مم
        m.do_follow_line_seg()
        segs = m.actions[-1][1]
        self.assertEqual(segs, [("follow_line", (-200, "L"))])


class ExecutionTests(unittest.TestCase):
    def test_cancel_brakes_instead_of_coasting(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 1000)]
        m.run_active = True
        m.run_cancel("اختبار")
        self.assertEqual(m.robot.braked, 1)
        self.assertFalse(m.run_active)

    def test_heartbeat_cancels_when_app_goes_silent(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 1000)]
        hub_loader.feed(m, "p")               # التطبيق بدأ يرسل نبضات
        m.beat_on = True
        m.run_active = True
        hubclock.advance(m.HEARTBEAT_MS + 1)
        _, out = capture(m.run_tick)
        self.assertFalse(m.run_active)
        self.assertIn("انقطاع الاتصال", out)

    def test_heartbeat_off_keeps_running(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 1000)]
        m.run_active = True
        m.run_speed = m.RUN_FOLLOW_SPEED
        hubclock.advance(m.HEARTBEAT_MS * 5)
        m.run_tick()
        self.assertTrue(m.run_active)

    def test_wheel_diameter_and_arm_motor_on_port_d(self):
        for m in (hub_loader.load_original(), hub_loader.load_app()):
            self.assertEqual(m.WHEEL_DIAMETER, 56)
            self.assertEqual(m.ARM_PORT_LETTER, "D")

        m = hub_loader.load_app()
        m.actions.clear()
        m.last_distance = 0
        m.last_heading = 0
        m.last_arm_angle = 0
        m.arm_motor.angle_value = 95
        m.do_record_move()
        self.assertEqual(m.actions[-1][1], [("arm", 95)])
        self.assertEqual(m.last_arm_angle, 95)

        # التراجع يعيد زاوية الذراع المرجعية
        m.do_undo()
        self.assertEqual(m.last_arm_angle, 0)

        # التحكم عن بعد بمحرك المنفذ D (u / j):
        # عند النقر السريع (وصول u ثم x في نفس الدورة) يستمر المحرك لـ RC_ARM_MIN_FRAMES دورات
        # حتى يتحرك الذراع فعليًا بدل التوقف في 0ms، ثم يتوقف تلقائيًا.
        hub_loader.feed(m, "u")
        self.assertTrue(m.rc_arm_driving)
        self.assertEqual(m.arm_motor.calls[-1], ("run", m.RC_ARM_SPEED))
        hub_loader.feed(m, "x")
        self.assertTrue(m.rc_arm_driving)
        for _ in range(m.RC_ARM_MIN_FRAMES):
            m.rc_tick()
        self.assertFalse(m.rc_arm_driving)

        # استلام وتنفيذ أمر محرك المنفذ D (M <angle>)
        hub_loader.feed(m, "KM -120\nE")
        self.assertEqual(m.run_queue, [("arm", -120)])
        m.arm_motor.angle_value = 0
        m.run_phase = "start"
        self.assertFalse(m._run_step_arm(-120))
        m.arm_motor.angle_value = -119
        self.assertTrue(m._run_step_arm(-120))
        self.assertGreaterEqual(m.arm_motor.braked, 1)


class AutoRecordWroTests(unittest.TestCase):
    """اختبارات التسجيل التلقائي الذكي للمسار بدون أزرار (WRO 2026)."""

    def _sample(self, m, n=1):
        for _ in range(n * m.AUTO_SAMPLE_EVERY):
            m.auto_read_tick()

    def test_auto_records_straight_and_snaps_90_turn_on_pause(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.AUTO_PRINT_PROG = False
        m.resync_tracking()
        m.line_sensor.reflection_value = 85

        # 1) دفع مستقيم 250 مم مع انحراف يد بسيط (3 درجات) ← يُتجاهل الانحراف ويُسجّل مستقيم صافٍ
        m.robot.distance_value = 250
        m.hub.imu.heading_value = 3
        self._sample(m, 1)
        self._sample(m, m.AUTO_SETTLE_TICKS)
        self.assertEqual(len(m.actions), 1)
        self.assertEqual(m.actions[-1][1], [("straight", 250)])
        self.assertEqual(m.last_heading, 0)  # بقي المرجع مثبّتًا عند 0°

        # 2) دوران باليد إلى 87 درجة ثم توقف ← يُثبّت تلقائيًا إلى 90 درجة بالضبط
        m.hub.imu.heading_value = 87
        self._sample(m, 1)
        self._sample(m, m.AUTO_SETTLE_TICKS)
        self.assertEqual(len(m.actions), 2)
        self.assertEqual(m.actions[-1][1], [("turn", 90)])
        self.assertEqual(m.last_heading, 90)

    def test_auto_detects_find_line_when_stopping_on_black(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.AUTO_PRINT_PROG = False
        m.resync_tracking()
        m.th_pinned = 45

        # يبدأ على الأبيض (88) ويتحرك حتى يقف فوق خط التوقف الأسود T-end (12)
        m.line_sensor.reflection_value = 88
        m.robot.distance_value = 90
        self._sample(m, 1)
        m.line_sensor.reflection_value = 12
        m.robot.distance_value = 180
        self._sample(m, 1)
        self._sample(m, m.AUTO_SETTLE_TICKS)

        self.assertEqual(len(m.actions), 1)
        self.assertEqual(m.actions[-1][1], [("find_line", (1, 180 + m.SEARCH_MARGIN))])

    def test_auto_detects_follow_line_when_walking_along_black_line(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.AUTO_PRINT_PROG = False
        m.resync_tracking()
        m.th_pinned = 45

        # يمشي 200 مم على الخط الأسود (قراءات داكنة متتالية)
        m.line_sensor.reflection_value = 15
        for step_d in (50, 100, 150, 200):
            m.robot.distance_value = step_d
            self._sample(m, 1)
        self._sample(m, m.AUTO_SETTLE_TICKS)

        self.assertEqual(len(m.actions), 1)
        self.assertEqual(m.actions[-1][1], [("follow_line", (200, m.FOLLOW_SIDE))])

    def test_auto_records_arm_port_d_and_toggles_commands(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.AUTO_PRINT_PROG = False
        m.resync_tracking()

        # تحريك محرك الذراع Port.D إلى -110 درجات ثم التوقف
        m.arm_motor.angle_value = -110
        self._sample(m, 1)
        self._sample(m, m.AUTO_SETTLE_TICKS)
        self.assertEqual(len(m.actions), 1)
        self.assertEqual(m.actions[-1][1], [("arm", -110)])

        # أوامر التحكم من التطبيق (m/n, g/h, i/o, 0)
        hub_loader.feed(m, "n")
        self.assertFalse(m.AUTO_RECORD)
        hub_loader.feed(m, "m")
        self.assertTrue(m.AUTO_RECORD)
        hub_loader.feed(m, "h")
        self.assertFalse(m.SNAP_90)
        hub_loader.feed(m, "g")
        self.assertTrue(m.SNAP_90)
        hub_loader.feed(m, "o")
        self.assertFalse(m.AUTO_LINE_DETECT)
        hub_loader.feed(m, "i")
        self.assertTrue(m.AUTO_LINE_DETECT)

        # الأمر 0 يمسح المسار ويصفّر نقطة القياس
        hub_loader.feed(m, "0")
        self.assertEqual(m.actions, [])

    def test_slow_hand_push_and_turn_pivot_roll_ignored(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.AUTO_PRINT_PROG = False
        m.resync_tracking()
        m.line_sensor.reflection_value = 85

        # 1) تحريك يدوي بطيء جدًا (4 مم كل 100ms، أقل من MOVE_EPS_DIST=8) لمسافة 100 مم
        for step in range(1, 26):
            m.robot.distance_value = step * 4
            self._sample(m, 1)
        # لم يُسجّل أثناء الحركة المستمرة
        self.assertEqual(len(m.actions), 0)
        # يتوقف لـ AUTO_SETTLE_TICKS دورات ← يُسجّل 100 مم كاملة
        self._sample(m, m.AUTO_SETTLE_TICKS)
        self.assertEqual(len(m.actions), 1)
        self.assertEqual(m.actions[-1][1], [("straight", 100)])

        # 2) لفّ الروبوت باليد 88 درجة مع دحرجة عجلات عرضية (22 مم) بسبب محور الدوران
        m.hub.imu.heading_value = 88
        m.robot.distance_value = 122
        self._sample(m, 1)
        self._sample(m, m.AUTO_SETTLE_TICKS)
        self.assertEqual(len(m.actions), 2)
        # يُسجّل الدوران فقط (90°) ويتجاهل دحرجة الـ 22 مم العرضية
        self.assertEqual(m.actions[-1][1], [("turn", 90)])
        self.assertEqual(m.last_distance, 122)


if __name__ == "__main__":
    unittest.main()
