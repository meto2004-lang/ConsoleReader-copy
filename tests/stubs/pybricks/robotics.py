"""DriveBase وهمي يسجّل الحركات بدل تنفيذها."""


class DriveBase:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.distance_value = 0
        self.angle_value = 0
        self.stopped = 0
        self.braked = 0

    def use_gyro(self, *args):
        pass

    def settings(self, **kwargs):
        self.calls.append(("settings", kwargs))

    def reset(self):
        pass

    def distance(self):
        return self.distance_value

    def angle(self):
        return self.angle_value

    def drive(self, speed, turn_rate):
        self.calls.append(("drive", speed, turn_rate))

    def stop(self):
        self.stopped += 1

    def brake(self):
        self.braked += 1

    def straight(self, dist):
        self.calls.append(("straight", dist))

    def turn(self, angle):
        self.calls.append(("turn", angle))
