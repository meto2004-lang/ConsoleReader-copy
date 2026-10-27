// اختبارات منطق التطبيق (JS) — تعمل بلا متصفح ولا روبوت.
// التشغيل:  node --test tests/web.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(root, "app/index.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

// نستخرج الدوال النقية فقط من داخل الصفحة (النص كله يعتمد على DOM).
function slice(from, to) {
  const start = script.indexOf(from);
  const end = script.indexOf(to, start);
  assert.ok(start >= 0 && end > start, "لم أجد الدالة " + from);
  return script.slice(start, end);
}

const pure = [
  slice("const progNum", "function setSendBusy"),
  slice("const FRAME_MAX", "async function sendProgramToRobot"),
].join("\n");
const api = new Function(pure + "\nreturn {"
  + " programToRobotLines, programThreshold, buildFrames, FRAME_MAX,"
  + " checkProgram, scanPython, libNormalize, libUpsert, libRemove,"
  + " parseHubList, pyFileName, LIB_MAX, PROG_NAME_MAX,"
  + " normalizeDigits, whyNoCommands };")();

const PROGRAM = `from pybricks.hubs import PrimeHub
robot = DriveBase(left_motor, right_motor, 62.4, 110)
LINE_THRESHOLD = 49  # محسوبة من قياساتك

def find_line(direction=1, max_dist=250, speed=80):
    robot.reset()
    robot.drive(direction * speed, 0)
    while abs(robot.distance()) < max_dist:
        robot.stop()
        return False
    robot.stop()
    return False

def run():
    robot.turn(-90)
    robot.straight(500)
    find_line(1, 250)
    align_on_line(25)
    follow_line(400, "L")
    follow_line(-250, side="R")
    robot.stop()          # غير مدعوم — يُتجاهل

run()
`;

test("يحوّل run() فقط ويتجاهل أجسام الدوال المساعدة", () => {
  const { lines, skipped } = api.programToRobotLines(PROGRAM);
  assert.deepEqual(lines, ["T -90", "S 500", "F 1 250", "A 25", "L 400 L", "L -250 R"]);
  // الأجسام الداخلية ليست «أسطرًا متجاهلة» — كان العدد 9 كإنذار كاذب
  assert.deepEqual(skipped, ["robot.stop()"]);
});

test("يقرأ عتبة الخط من اللوحة", () => {
  assert.equal(api.programThreshold(PROGRAM), 49);
  assert.equal(api.programThreshold("robot.straight(100)"), null);
});

test("يبني حزمًا بحجم آمن ويعيد تجميع النص نفسه", () => {
  const text = PROGRAM.split("\n").filter(l => /^(robot\.|find_line|follow_line)/.test(l.trim())).join("\n");
  const frames = api.buildFrames(text, 17);
  const decoder = new TextDecoder();
  let rebuilt = "";
  for (const f of frames) {
    assert.equal(f[0], 78);                       // 'N'
    const len = f[1] | (f[2] << 8);
    assert.equal(len, f.length - 3);
    assert.ok(f.length <= api.FRAME_MAX + 3);     // لا تتجاوز حدّ خاصية BLE
    rebuilt += decoder.decode(f.subarray(3));
  }
  assert.equal(rebuilt, text);
});

test("حزمة واحدة لكل 90 بايت كحد أقصى", () => {
  const frames = api.buildFrames("x".repeat(1000));
  assert.equal(frames.length, 12);
  assert.ok(frames.every(f => f.length <= 93));
});

test("سطر القياس يخصّ حسّاسًا واحدًا على C (لا L/R)", () => {
  // الحسّاس الوحيد على المنفذ C: البثّ والـ CSV يجب ألا يذكرا L/R
  const telRe = script.match(/const tel = line\.match\(\/(.+?)\/\);/);
  assert.ok(telRe, "لم أجد سطر تحليل # T");
  const re = new RegExp(telRe[1]);
  const sample = "# T d=120 h=-45 C=33";
  const m = sample.match(re);
  assert.ok(m, "سطر القياس الجديد لم يُطابق");
  assert.deepEqual(m.slice(1), ["120", "-45", "33"]);
  assert.equal(("# T d=120 h=-45 L=33 R=34").match(re), null);   // صيغة قديمة = مرفوضة

  assert.match(script, /\["t_s", "d_mm", "h_deg", "C_reflect"\]/);  // ترويسة CSV
  assert.match(script, /rows\.push\(\[s\.t, s\.d, s\.h, s\.C\]\)/);
  assert.doesNotMatch(script, /L_reflect|R_reflect/);
  assert.doesNotMatch(script, /L=\(\[|R=\(\[/);            // لا التقاط لقيم الحسّاسين
});

// ================= استوديو البرمجة =================
const GOOD = `LINE_THRESHOLD = 42  # عتبة
def run():
    robot.turn(90)
    robot.straight(300)
    find_line(1, 250)
    align_on_line(25)
    follow_line(400, "L")
    follow_line(-200, side="R")

run()
`;

test("الفحص يقبل برنامجًا سليمًا ويعدّ الأوامر بدقة", () => {
  const r = api.checkProgram(GOOD);
  assert.equal(r.ok, true, r.errors.join(" | "));
  assert.equal(r.lines, 6);
  assert.equal(r.threshold, 42);
  assert.deepEqual(r.skipped, []);
  assert.deepEqual(r.errors, []);
});

test("الفحص يمنع البرنامج الناقص (قوس لم يُغلق) ويذكر السطر", () => {
  const r = api.checkProgram("robot.turn(90\nrobot.straight(200)\n");
  assert.equal(r.ok, false);
  assert.match(r.errors.join(" "), /سطر 1/);
});

test("الفحص لا يتأثر بالأقواس داخل النصوص والتعليقات", () => {
  const r = api.checkProgram('LINE_THRESHOLD = 40\n# robot.turn(90 (ناقص\nprint("(")\nrobot.straight(100)\n');
  assert.equal(r.ok, true, r.errors.join(" | "));
  assert.equal(r.lines, 1);
});

test("الفحص يرفض محرّرًا فارغًا أو بلا أوامر مدعومة", () => {
  assert.equal(api.checkProgram("").ok, false);
  const r = api.checkProgram("robot.stop()\nwait(100)\n");
  assert.equal(r.ok, false);
  assert.match(r.errors.join(" "), /قابل للإرسال/);
});

test("الفحص يحذّر من الأسطر غير المدعومة ويعدّها", () => {
  const r = api.checkProgram("robot.turn(90)\nrobot.stop()\n");
  assert.equal(r.ok, true);
  assert.equal(r.lines, 1);
  assert.equal(r.skipped.length, 1);
  assert.match(r.warnings.join(" "), /robot\.stop\(\)/);
});

test("الفحص يرفض أكثر من 90 أمرًا (حدّ الـ Hub)", () => {
  const many = "robot.straight(10)\n".repeat(91);
  const r = api.checkProgram(many);
  assert.equal(r.ok, false);
  assert.match(r.errors.join(" "), /90/);
});

test("الفحص يحذّر عندما يستخدم الخط بلا LINE_THRESHOLD", () => {
  const r = api.checkProgram("find_line(1, 250)\nfollow_line(300, \"L\")\n");
  assert.equal(r.ok, true);
  assert.equal(r.threshold, null);
  assert.match(r.warnings.join(" "), /LINE_THRESHOLD/);
});

test("المكتبة: الاستبدال بالاسم نفسه وإبقاء الأحدث أولًا", () => {
  let lib = [];
  lib = api.libUpsert(lib, "أ", "robot.turn(10)", 1);
  lib = api.libUpsert(lib, "ب", "robot.turn(20)", 2);
  assert.deepEqual(lib.map(x => x.name), ["ب", "أ"]);
  lib = api.libUpsert(lib, "أ", "robot.turn(30)", 3);
  assert.equal(lib.length, 2);
  assert.equal(lib.find(x => x.name === "أ").code, "robot.turn(30)");
});

test("المكتبة: تنظيف المدخلات الفاسدة وحدّ أقصى", () => {
  assert.deepEqual(api.libNormalize("bad"), []);
  assert.deepEqual(api.libNormalize([null, { name: "", code: "x" }, { name: "ن", code: "  " }]), []);
  const big = [];
  for (let i = 0; i < 60; i++) big.push({ name: "p" + i, code: "robot.turn(1)" });
  assert.equal(api.libNormalize(big).length, api.LIB_MAX);
  assert.equal(api.libNormalize([{ name: "ن", code: "x", updated: "??" }])[0].updated, 0);
});

test("المكتبة: الحذف بالاسم", () => {
  const lib = [{ name: "أ", code: "x" }, { name: "ب", code: "y" }];
  assert.deepEqual(api.libRemove(lib, "أ").map(x => x.name), ["ب"]);
  assert.deepEqual(api.libRemove(lib, "غير موجود").map(x => x.name), ["أ", "ب"]);
});

test("قائمة برامج الـ Hub تُقرأ من سطور V", () => {
  const out = api.parseHubList([
    "# V 2",
    "# P 0 5 خط أول",
    "# P 1 9 مسار طويل",
    "# V end",
    "# إشعار عادي",
  ]);
  assert.deepEqual(out, [
    { index: 0, count: 5, name: "خط أول" },
    { index: 1, count: 9, name: "مسار طويل" },
  ]);
});

test("اسم الملف آمن ويحفظ العربية", () => {
  assert.equal(api.pyFileName("مسار/سريع"), "مسار_سريع.py");
  assert.equal(api.pyFileName(""), "program.py");
  assert.ok(api.pyFileName("a b").indexOf(" ") < 0);
  assert.equal(api.PROG_NAME_MAX, 20);        // نفس PROG_NAME_MAX في as3_app.py
});

// ===== حالات كانت تُنتج «لم أجد أوامر قابلة للإرسال» =====
test("أرقام عربية/فارسية تُحوَّل إلى لاتينية (لوحة مفاتيح عربية)", () => {
  assert.equal(api.normalizeDigits("robot.turn(٩٠)"), "robot.turn(90)");
  assert.equal(api.normalizeDigits("robot.turn(۹۰)"), "robot.turn(90)");
  assert.equal(api.normalizeDigits("S ٤٠٠"), "S 400");
  assert.equal(api.normalizeDigits("abc"), "abc");
  const { lines } = api.programToRobotLines("robot.turn(٩٠)\nrobot.straight(٣٠٠)\n");
  assert.deepEqual(lines, ["T 90", "S 300"]);
});

test("run() فقد مسافاته البادئة: الخطة البديلة تُنجح الإرسال", () => {
  const src = "def run():\nrobot.turn(90)\nrobot.straight(200)\n";
  assert.deepEqual(api.programToRobotLines(src).lines, ["T 90", "S 200"]);
});

test("أمران في سطر واحد مفصولان بفاصلة منقوطة", () => {
  assert.deepEqual(api.programToRobotLines("robot.turn(90); robot.straight(200)\n").lines,
    ["T 90", "S 200"]);
});

test("أجسام الدوال المساعدة لا تُنفَّذ حتى في الخطة البديلة", () => {
  const src = [
    "def find_line(direction=1, max_dist=250):",
    "    robot.reset()",
    "    robot.straight(999)",          // داخل الدالة المساعدة: ليس أمر مسار
    "    return True",
    "robot.straight(300)",
    "",
  ].join("\n");
  assert.deepEqual(api.programToRobotLines(src).lines, ["S 300"]);
});

test("البرنامج المولَّد يبقى كما هو (لا انحدار في السلوك الأصلي)", () => {
  const gen = [
    "robot.use_gyro(True)",
    "robot.settings(straight_acceleration=1200, turn_acceleration=1500)",
    "def follow_line(dist, side=\"L\", speed=90):",
    "    robot.drive(spd, sign * (2.5) * error)",
    "def run():",
    "    robot.turn(-90)",
    "    find_line(1, 250)",
    "    follow_line(400, \"L\")",
    "run()",
    "",
  ].join("\n");
  const r = api.programToRobotLines(gen);
  assert.deepEqual(r.lines, ["T -90", "F 1 250", "L 400 L"]);
  assert.deepEqual(r.skipped, []);
});

test("رسالة السبب تفرّق بين «لا أوامر» و«أوامر غير مدعومة»", () => {
  const empty = api.programToRobotLines("print('hello')\n");
  assert.match(api.whyNoCommands("print('hello')\n", empty), /لا يوجد أي سطر فيه/);

  const unsupported = api.programToRobotLines("robot.stop()\nwait(100)\n");
  assert.match(api.whyNoCommands("robot.stop()\nwait(100)\n", unsupported), /غير مدعومة/);

  const outsideRun = api.programToRobotLines("def helper():\n    robot.turn(90)\n");
  assert.match(api.whyNoCommands("def helper():\n    robot.turn(90)\n", outsideRun),
    /داخل دالة|غير مدعومة/);
});

test("يحوّل أوامر محرك المنفذ D (arm_motor.run_angle) إلى M", () => {
  const src = "def run():\n    arm_motor.run_angle(300, 90)\n    arm_motor.run_angle(-45)\nrun()\n";
  const r = api.programToRobotLines(src);
  assert.deepEqual(r.lines, ["M 90", "M -45"]);
  assert.deepEqual(r.skipped, []);
  const chk = api.checkProgram(src);
  assert.equal(chk.ok, true, chk.errors.join(" | "));
  assert.equal(chk.lines, 2);
});

test("الفحص يعرض السبب ويذكر تحويل الأرقام", () => {

  const bad = api.checkProgram("print('x')\n");
  assert.equal(bad.ok, false);
  assert.match(bad.errors.join(" "), /لا يوجد أي أمر حركة/);

  const arabic = api.checkProgram("robot.turn(٩٠)\n");
  assert.equal(arabic.ok, true, arabic.errors.join(" | "));
  assert.equal(arabic.lines, 1);
  assert.match(arabic.notes.join(" "), /حُوّلت الأرقام العربية/);
});
