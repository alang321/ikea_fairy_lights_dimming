# IKEA LED strip controller hijack — project context

Goal: make a 24 V IKEA LED strip smoothly dimmable (plus a simple web UI) by replacing the original controller's microcontroller with a Raspberry Pi Pico W, while reusing the original board's H-bridge.

Current status: **working.** The original MCU (U1) is removed, the Pico W drives the bridge via PIO, and the strip fades with the test script (`bridge.py`, included below).

---

## Hardware

### LED strip
- IKEA 24 V strip, **2 wires, LEDs in anti-parallel** (half the LEDs light per polarity), so it needs an **alternating-polarity H-bridge**. A single low-side switch would only ever light half of it.
- Current: roughly 0.15 A (not yet verified by measurement).

### Original controller board (silkscreen "103305 Rev:02")
- Pads: `V+`, `V-` (supply in), `L1`, `L2` (strip out; silkscreen font makes them look like "LF"/"LZ").
- **D2**: series diode right after V+ (reverse-polarity protection).
- **U2**: 78L05 regulator (SOT-89), was powering U1 at 5 V.
- **U1** (REMOVED): 10-pin MSOP MCU marked "D681" with a logo, unidentifiable, almost certainly OTP/mask ROM. Pin 1 at the dot; pins 1–5 one row, 6–10 the other.
- **S1 / S2**: tactile buttons (on/off and mode). They switch a U1 input to GND. Not yet mapped to U1 pins.
- **PT1**: 2-leg clear part, likely a phototransistor (dusk sensor). Not yet mapped.
- **L0**: small orange indicator LED. Not yet mapped.
- **R11–R14**: 10 Ω (marked 10R0), probably output current limiting. Exact position in the path not verified.
- Four round copper test pads around U1 (likely factory programming pads, irrelevant now).

### H-bridge (measured / confirmed)
Cross-coupled complementary MOSFET bridge:
- **Low side**: Q1 (drain → L2), Q2 (drain → L1), N-channel (marked "AFOV/A0FV", probably AO3400-type), sources to GND.
- **High side**: Q3 (drain → L1), Q4 (drain → L2), P-channel AO3401 ("3401"), sources on V+ (via D2).
- **Low-side gate drive**: U1 pin → 1 kΩ (102) → gate, with 10 kΩ (103) gate-to-GND pull-down.
  - **U1 pin 5 → Q1** (pulls L2 low)
  - **U1 pin 8 → Q2** (pulls L1 low)
- **High-side gate drive (cross-coupling)**: each P-gate has about 2 kΩ pull-up to V+ and 10 kΩ to the **opposite** output. Measured for Q3: 2 kΩ to V+, 10 kΩ to L2. Q4 assumed mirrored (2 kΩ to V+, 10 kΩ to L1).
  - When Q1 pulls L2 low, Q3's gate gets divided to about V+ × 2/12 ≈ 4 V below V+, so Q3 turns on and L1 = V+. The current path is V+ → Q3 → L1 → strip → L2 → Q1 → GND.
  - **So one control line per polarity:** pin 5 drives "L1 high / L2 low", pin 8 drives "L2 high / L1 low".
- **Idle/off state**: with both low sides off, both outputs float up to V+ through the ~12 kΩ gate networks, so the strip sees 0 V. On the scope "both outputs at V+" means off. This is normal.

### Original firmware behaviour (measured with Rigol DS1054Z)
- Time base of 2.5 ms per phase; full polarity cycle 5 ms (**200 Hz**).
- Off = both outputs high; a driven phase = one output pulled low.
- **Dead time between polarities: 22 µs** (measured from L1 drive ending to L2 drive starting; opposite changeover not separately measured).
- L1 rises slowly and exponentially after release (floating), and snaps to V+ when the opposite low side turns on. The L2 falling edge has a small kink, most likely the Miller plateau, judged harmless.

---

## Current wiring (development)
| Pico W | Board |
|---|---|
| GP0 (physical pin 1) | old U1 pin 5 pad → Q1 |
| GP1 (physical pin 2) | old U1 pin 8 pad → Q2 |
| GND (physical pin 3) | V- |

- The Pico is powered from laptop USB, with grounds tied (Pico GND ↔ V-).
- The board is powered from a bench supply at 24 V with a current limit (~250 mA with the strip connected).
- 3.3 V drive through the 1k/10k divider gives about 3.0 V on the gate, which is enough for an AO3400-type MOSFET.
- The 10 kΩ pull-downs keep the bridge off while the Pico boots or its pins float.

---

## Hard safety rules (must hold in all firmware)
1. **GP0 and GP1 must never be high at the same time.** Both low sides on means both high sides on, which shorts V+ to GND on both legs (shoot-through).
2. **Dead time ≥ 30 µs** between one drive ending and the other starting (the original uses 22 µs; 30 µs adds margin). The high side turns off slowly through its 2 kΩ pull-up.
3. Clamp the maximum pulse width so the dead time can never shrink.
4. The PIO state machine must receive a valid setting **before** `sm.active(1)`: `pull(noblock)` reuses X, which starts at 0, and a zero-off-count would violate the dead time.
5. Never connect a 5 V signal from the board (old button pull-ups, sensor, 78L05 rail) directly to a Pico GPIO.
6. For any timing change, test first without the strip: the supply should draw only a few mA. Raising the polarity rate (e.g. to 10 kHz) temporarily makes shoot-through visible as rising average current.

---

## Firmware design (current)
- MicroPython on Pico W (RPI_PICO_W UF2), developed with Thonny / mpremote on Ubuntu.
- **PIO state machine** drives both pins in sequence: pulse on GP0, gap, pulse on GP1, gap. Overlap is impossible by construction.
- PIO clock 10 MHz (0.1 µs per cycle), polarity cycle 1 kHz (5000 cycles per half), dead time 300 cycles.
- One 32-bit FIFO word per setting: low 16 bits = on count, high 16 bits = off count.
- Cycle accounting: on duration = y_on + 2 cycles; off segment ≈ y_off + 5 (or 6) cycles; `MAX_ON = HALF - DEAD - 6`.
- `set_brightness(0..1)` uses gamma 2.2. At 0 it stops the SM and drives both pins low as plain GPIO.
- Scheme: alternate polarity on every pulse (one pulse per half-cycle); brightness = pulse width.

### bridge.py (working)
```python
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
```

---

## Next steps / ideas
1. **Web interface** on the Pico W: Wi-Fi station mode plus a small HTTP server (e.g. Microdot or a plain asyncio socket server), with a brightness slider and on/off. Brightness changes should go through `set_brightness`; consider smooth fading between values.
2. **Persist settings** (last brightness, on/off) to a small file in flash.
3. **Low-end smoothness**: below the minimum clean pulse (~a few µs, limited by the high-side turn-on through 10 kΩ), dim further by pulse skipping (e.g. drive only every 2nd/4th cycle). Verify the dark end visually and on the scope.
4. **Reuse the buttons (optional)**: trace which old U1 pads connect to S1/S2 (button to GND when pressed). Check whether those pads carry a pull-up to 5 V before connecting; prefer the Pico's internal pull-ups and remove or avoid any 5 V pull-up.
5. **Reuse the phototransistor (optional)**: trace PT1's circuit first. If it's referenced to 5 V, divide it down before the Pico ADC (max 3.3 V).
6. **Standalone power**: run the Pico from the 24 V supply with a buck converter set to 5 V (or 3.3 V) into **VSYS** (pin 39), through a Schottky diode if USB may also be connected. Don't use the board's 78L05 (100 mA is too little for Wi-Fi peaks).
7. **Optional checks**: measure the opposite changeover dead time; verify Q4's gate network mirrors Q3's; verify strip current; run the 10 kHz shoot-through current test without the strip.

## Test equipment available
- Rigol DS1054Z: probe grounds **only** on V-; 10× probes; trigger on the falling edge of the active output (outputs idle at V+); Math CH1−CH2 shows the voltage across the strip.
- Programmable bench supply (current limit for all tests).
- UNI-T UT161 multimeter.
