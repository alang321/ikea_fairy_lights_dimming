# Brightness state, smooth fading, and remembering the last setting in flash
import asyncio
import json
import math
import time
import bridge

STATE_FILE = "state.json"
TICK_MS = 5             # fader update interval (200 Hz)
SLIDE_TAU_MS = 40       # smoothing while dragging: short, only hides Wi-Fi jitter
TOGGLE_MS = 400         # on/off fade duration
SAVE_DELAY_MS = 3000    # write to flash only once the setting has settled
MAX_LEVEL = 0.93        # slider 100% -> 93% (~85% power): keeps strip + Pico under the 0.15 A supply


def _clamp(b):
    return min(1.0, max(0.0, b)) if b == b else 0.0   # b != b catches NaN


class Light:
    def __init__(self):
        self.level = 0.5        # slider position 0..1 (perceptual, gamma is applied in bridge)
        self.on = False
        self._out = 0.0         # brightness currently applied to the bridge
        self._ramp = None       # (start value, start ms) while an on/off fade runs
        self._dirty_at = None
        self._load()

    def state(self):
        return {"b": round(self.level, 4), "on": self.on}

    def set_level(self, b):
        """From the slider: follow closely."""
        self.level = _clamp(b)
        self.on = self.level > 0
        self._ramp = None
        self._dirty_at = time.ticks_ms()

    def set_on(self, on):
        """From the button: fade over TOGGLE_MS."""
        if on and self.level < 0.01:
            self.level = 0.5
        self.on = on
        self._ramp = (self._out, time.ticks_ms())
        self._dirty_at = time.ticks_ms()

    async def run(self):
        k = 1 - math.exp(-TICK_MS / SLIDE_TAU_MS)
        if self.on:                                  # fade in to the restored setting at power-up
            self._ramp = (0.0, time.ticks_ms())
        while True:
            target = self.level if self.on else 0.0
            if self._ramp:
                start, t0 = self._ramp
                f = time.ticks_diff(time.ticks_ms(), t0) / TOGGLE_MS
                if f >= 1:
                    out, self._ramp = target, None
                else:
                    out = start + (target - start) * f * f * (3 - 2 * f)   # smoothstep
            else:
                out = self._out + (target - self._out) * k
                if abs(target - out) < 0.001:
                    out = target
            if out != self._out:
                self._out = out
                bridge.set_brightness(out * MAX_LEVEL)
            if self._dirty_at is not None and time.ticks_diff(time.ticks_ms(), self._dirty_at) > SAVE_DELAY_MS:
                self._save()
            await asyncio.sleep_ms(TICK_MS)

    def _save(self):
        self._dirty_at = None
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.state(), f)
        except OSError as e:
            print("save failed:", e)

    def _load(self):
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
            self.level = _clamp(float(s["b"]))
            self.on = bool(s["on"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
