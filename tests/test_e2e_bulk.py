"""اختبار شامل عبر اللغتين: JS (البناء) → Python (الفك).

يأخذ برنامج سباق حقيقيًا من `as3_app.py`، يحوّله بـ `programToRobotLines`
داخل `app/index.html` (عبر Node)، يبني حزم `N` بـ `buildFrames`، ثم يغذّي
البايتات إلى آلة استلام الـ Hub ويتحقق أن قائمة التنفيذ تطابق البرنامج.

يُتخطّى تلقائيًا إن لم يكن Node مثبتًا.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import hub_loader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")

BUILD_JS = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const cut = (a, b) => script.slice(script.indexOf(a), script.indexOf(b, script.indexOf(a)));
const pure = cut("const progNum", "function setSendBusy") + "\n" +
             cut("const FRAME_MAX", "async function sendProgramToRobot");
const api = new Function(pure + "\nreturn {programToRobotLines, programThreshold, buildFrames};")();
const program = fs.readFileSync(process.argv[3], "utf8");
const out = api.programToRobotLines(program);
const text = out.lines.map(l => l + "\n").join("");
// تقسيم قسري صغير لاختبار انقسام الأسطر بين الحزم
const frames = api.buildFrames(text, 17).map(f => Array.from(f));
process.stdout.write(JSON.stringify({
  lines: out.lines, skipped: out.skipped,
  threshold: api.programThreshold(program), frames
}));
"""


def generated_program():
    module = hub_loader.load_app()
    module.actions.clear()
    module.refl.clear()
    module.refl.add(9)
    module.refl.add(88)
    module.actions.append(("move", [("turn", -92), ("straight", 504)], 0, 0))
    module.actions.append(("move", [("find_line", (1, 255)), ("align_line", 25)], 504, -92))
    module.actions.append(("move", [("follow_line", (412, "L"))], 600, 0))
    module.actions.append(("move", [("follow_line", (-250, "R"))], 1000, 0))
    module.actions.append(("move", [("straight", -130)], 1250, 0))
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        module.print_full_program()
    out = buf.getvalue()
    return out.split("#@@PROGRAM_BEGIN@@")[1].split("#@@PROGRAM_END@@")[0]


@unittest.skipIf(NODE is None, "Node غير مثبت — تخطّي اختبار اللغتين")
class CrossLanguageTests(unittest.TestCase):
    def test_js_frames_reach_hub_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            program_path = os.path.join(tmp, "prog.py")
            js_path = os.path.join(tmp, "build.js")
            with open(program_path, "w", encoding="utf-8") as handle:
                handle.write(generated_program())
            with open(js_path, "w", encoding="utf-8") as handle:
                handle.write(BUILD_JS)
            result = subprocess.run(
                [NODE, js_path, os.path.join(ROOT, "app", "index.html"), program_path],
                capture_output=True, check=True, timeout=60,
            )
        built = json.loads(result.stdout.decode("utf-8"))

        self.assertEqual(built["skipped"], [])
        self.assertEqual(built["threshold"], 48)
        self.assertEqual(built["lines"],
                         ["T -92", "S 504", "F 1 255", "A 25", "L 412 L", "L -250 R", "S -130"])

        module = hub_loader.load_app()
        wire = "B" + "".join(chr(b) for frame in built["frames"] for b in frame) + "E"
        hub_loader.feed(module, wire + "H " + str(built["threshold"]) + "\n")

        self.assertFalse(module.code_mode)
        self.assertEqual(module.run_th, 48)
        self.assertEqual(module.run_queue, [
            ("turn", -92), ("straight", 504), ("find_line", 1, 255),
            ("align_line", 25), ("follow_line", 412, "L"),
            ("follow_line", -250, "R"), ("straight", -130),
        ])


if __name__ == "__main__":
    unittest.main()
