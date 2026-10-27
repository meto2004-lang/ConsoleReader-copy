import hubclock


def wait(ms):
    hubclock.advance(ms)


class StopWatch:
    def __init__(self):
        self._start = hubclock.now()

    def reset(self):
        self._start = hubclock.now()

    def time(self):
        return hubclock.now() - self._start
