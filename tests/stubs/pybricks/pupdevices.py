"""محركات وحساسات وهمية تُعيد قراءات قابلة للضبط."""


class Motor:
    def __init__(self, *args, **kwargs):
        self.stopped = 0
        self.braked = 0
        self.angle_value = 0
        self.calls = []

    def stop(self):
        self.stopped += 1

    def brake(self):
        self.braked += 1

    def angle(self):
        return self.angle_value

    def reset_angle(self, val=0):
        self.angle_value = val

    def run(self, speed):
        self.calls.append(("run", speed))

    def run_angle(self, speed, rotation_angle, *args, **kwargs):
        self.angle_value += rotation_angle
        self.calls.append(("run_angle", speed, rotation_angle))


class ColorSensor:
    def __init__(self, *args, **kwargs):
        self.reflection_value = 90

    def color(self):
        return None

    def reflection(self):
        return self.reflection_value

    def ambient(self):
        return 0

    def hsv(self):
        return (0, 0, 0)
