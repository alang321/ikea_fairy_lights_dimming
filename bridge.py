# Pico W H-bridge driver for the hijacked LED controller board
# GP0 -> old U1 pin 5 (drives Q1, L2 low / L1 high)
# GP1 -> old U1 pin 8 (drives Q2, L1 low / L2 high)
# Pico GND -> board V-
import rp2
from machine import Pin

SM_FREQ = 10_000_000          # PIO clock: 1 cycle = 0.1 us
POL_HZ = 1000                 # full polarity cycles per second
DEAD_US = 30                  # minimum gap between the two drives (measured original: 22 us)

HALF = SM_FREQ // (2 * POL_HZ)          # cycles per half-cycle (5000)
DEAD = DEAD_US * SM_FREQ // 1_000_000   # dead time in cycles (300)
MAX_ON = HALF - DEAD - 6                # longest allowed pulse, keeps dead time guaranteed

@rp2.asm_pio(set_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW),
             out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def bridge():
    wrap_target()
    pull(noblock)          # new setting if available, otherwise X is reused
    mov(x, osr)
    # --- phase A: GP0 on ---
    out(y, 16)             # low 16 bits: on count
    set(pins, 0b01)
    label("on_a")
    jmp(y_dec, "on_a")
    set(pins, 0b00)
    out(y, 16)             # high 16 bits: off count (includes dead time)
    label("off_a")
    jmp(y_dec, "off_a")
    # --- phase B: GP1 on ---
    mov(osr, x)
    out(y, 16)
    set(pins, 0b10)
    label("on_b")
    jmp(y_dec, "on_b")
    set(pins, 0b00)
    out(y, 16)
    label("off_b")
    jmp(y_dec, "off_b")
    wrap()

sm = None

def _pins_low():
    Pin(0, Pin.OUT, value=0)
    Pin(1, Pin.OUT, value=0)

def _word(on_cycles):
    on_cycles = max(2, min(on_cycles, MAX_ON))
    y_on = on_cycles - 2
    y_off = HALF - on_cycles - 6        # always >= DEAD because on_cycles <= MAX_ON
    return (y_off << 16) | y_on

def set_brightness(b):
    """b from 0.0 (off) to 1.0 (max). Gamma-corrected."""
    global sm
    b = max(0.0, min(1.0, b))
    on_cycles = round(MAX_ON * b ** 2.2)
    if on_cycles < 2:                   # off: stop PIO and hold both pins low
        if sm:
            sm.active(0)
            sm = None
        _pins_low()
        return
    if sm is None:
        sm = rp2.StateMachine(0, bridge, freq=SM_FREQ, set_base=Pin(0))
        sm.put(_word(on_cycles))        # valid setting BEFORE starting
        sm.active(1)
    else:
        sm.put(_word(on_cycles))

def off():
    set_brightness(0)

# --- simple test: fade up and down, Ctrl-C to stop ---
if __name__ == "__main__":
    import time
    try:
        while True:
            for i in range(0, 101, 2):
                set_brightness(i / 100); time.sleep_ms(30)
            for i in range(100, -1, -2):
                set_brightness(i / 100); time.sleep_ms(30)
    finally:
        off()