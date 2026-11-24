"""Reference for the Assist fade-in (Andy Nov 24 16:00-16:04), used by the page tests and as
the test vectors for the model (16g, Simulink thread).

Rule:
- Assist off -> on: cap = 0, ramp active. RL-AAN (or Fixed K) is engaged and keeps updating
  its level every stride as usual.
- At each heel strike while the ramp is active: cap += step; applied = min(cap, level in use
  at that stride). The ramp is DONE at the first heel strike where cap >= the CURRENT level
  (not the level read at Assist on); from then on applied = level.
- Between heel strikes nothing changes (the level only updates at heel strike, as in 16f).
- Assist off: applied 0 immediately, cap reset; the next Assist on starts a new ramp.
- step 0 = ramp off (the old immediate behaviour).
"""


class AssistRamp:
    def __init__(self, step=1.0):
        self.step = float(step)
        self.assist = False
        self.active = False
        self.cap = 0.0
        self.applied = 0.0

    def set_assist(self, on: bool) -> float:
        on = bool(on)
        if on and not self.assist:
            self.cap = 0.0
            self.active = self.step > 0
            self.applied = 0.0                 # nothing until the first heel strike after Assist on
        elif not on:
            self.active, self.cap, self.applied = False, 0.0, 0.0
        self.assist = on
        return self.applied

    def heel_strike(self, level: float) -> float:
        if not self.assist:
            self.applied = 0.0
            return self.applied
        level = float(level)
        if self.active:
            self.cap += self.step
            if self.cap >= level:
                self.active = False
                self.applied = level
            else:
                self.applied = min(self.cap, level)
        else:
            self.applied = level
        return self.applied
