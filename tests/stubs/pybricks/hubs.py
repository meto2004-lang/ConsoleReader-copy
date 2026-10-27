"""Hub وهمي: لا أزرار مضغوطة، اتجاه ثابت، وطابور أصوات للتفتيش."""


class _Buttons:
    def pressed(self):
        return []


class _Imu:
    def __init__(self):
        self.heading_value = 0.0

    def heading(self):
        return self.heading_value

    def reset_heading(self, angle=0):
        # يستخدمه برنامج المعايرة tools/xy_calibrate.py
        self.heading_value = angle


class _Speaker:
    def __init__(self):
        self.beeps = []

    def beep(self, freq, ms):
        self.beeps.append((freq, ms))


class _Light:
    def __init__(self):
        self.color = None

    def on(self, color):
        self.color = color


class PrimeHub:
    def __init__(self):
        self.buttons = _Buttons()
        self.imu = _Imu()
        self.speaker = _Speaker()
        self.light = _Light()
