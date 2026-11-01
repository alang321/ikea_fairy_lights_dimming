# IKEA light strip controller (Pico W)

Smoothly dimmable 24 V IKEA LED strip, controlled from your phone over the local network.
The original controller's microcontroller (U1) was removed; a Raspberry Pi Pico W now drives
the board's H-bridge directly. Hardware details and measurements are in
[`led-controller-context.md`](led-controller-context.md).

Open **http://lightstrip.fritz.box/** (or **http://192.168.178.38/**) on a phone on the same Wi-Fi:
one big slider plus an on/off button.

## Files (all copied to the Pico)

| File | What it does |
|---|---|
| `main.py` | Runs at power-up: OTA server, fader, web server, and Wi-Fi with a self-check (see below) |
| `ota.py` | Updates over Wi-Fi (port 8080, token-protected). Independent of the app, so it survives a broken `light.py`/`web.py` |
| `bridge.py` | H-bridge driver (PIO). Enforces the safety rules: never both outputs on, ≥ 30 µs dead time |
| `light.py` | Brightness state, smooth fading, brightness cap, saves the last setting to flash |
| `web.py` | Serves the page and a WebSocket for live control (no external libraries) |
| `index.html` | The phone page |
| `config.py` | Wi-Fi networks, hostname, country code, OTA token. **Contains secrets, don't share it** |
| `state.json` | Created on the Pico: last brightness and on/off, restored at power-up |
| `net.log` | Created on the Pico: connects, outages, reconnects and errors (UTC) |

Laptop-only tools: `push.py` (updates over Wi-Fi) and `dev_server.py` (local preview of the page).

## Wiring

| Pico W | Board |
|---|---|
| GP0 (pin 1) | old U1 pin 5 pad → Q1 (L1 high / L2 low) |
| GP1 (pin 2) | old U1 pin 8 pad → Q2 (L2 high / L1 low) |
| GND (pin 3) | V− |

### Standalone power (instead of USB)

```
24 V (V+) ──► buck 24→3.3 V ──►|── VSYS (pin 39)
V− ─────────► buck GND ─────────── GND  (pin 38)
                          Schottky diode (e.g. 1N5819), needed if USB may also be plugged in
```

- Use **VSYS**, not the 3V3 pin. VSYS accepts 1.8–5.5 V.
- The buck converter must be rated for ≥ 28 V input (not the 23 V "Mini-360" type). Set it to 3.3 V before connecting.
- Current budget at 24 V: strip at the 93 % cap ≈ 117 mA + Pico ≈ 20 mA (Wi-Fi spikes ~40 mA) ≈ 137 mA, under the 0.15 A supply.

## Updating over Wi-Fi (normal way)

```bash
python3 push.py light.py index.html   # upload; reboots automatically if a .py file changed
python3 push.py --log                 # connection/outage/error log
python3 push.py --ls | --get <file> | --reboot
```

`.py` files are syntax-checked on the Pico before they replace the old file. A logic bug in
`light.py`/`web.py` still leaves the OTA server running. Only `main.py`, `ota.py` and `config.py`
can break updates over Wi-Fi if wrong (push.py asks before uploading those). A reboot turns the
light off for ~5 s, then it fades back to its saved state. `index.html` needs no reboot.

## Previewing the page locally

```bash
python3 dev_server.py        # http://localhost:8000/, also reachable from the phone via the laptop's IP
```

Uses the real `web.py` with a fake light. Edit `index.html` and refresh. When happy: `python3 push.py index.html`.

## First install over USB

Needs [`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html) (`pip install mpremote`)
and MicroPython for the Pico W (tested with v1.29). Close Thonny first; it holds the USB port.

```bash
# cp config.example.py config.py, then fill in NETWORKS, COUNTRY, OTA_TOKEN
mpremote cp bridge.py light.py web.py ota.py index.html config.py main.py : + reset
```

The on-board LED is lit while connecting to Wi-Fi. Connecting with Thonny or mpremote stops the
program; unplug/replug or press Ctrl-D to start it again.

## How it works

- **Phone → Pico:** the page keeps one WebSocket open and sends the slider value up to ~60×/s.
  If the network is busy it drops stale values, so the light always follows the latest position.
  The connection closes when the phone locks and reconnects when you come back.
- **Pico:** a 200 Hz fader eases toward the target (≈40 ms smoothing while dragging, 0.4 s fade for
  on/off) and calls `bridge.set_brightness()`, which applies gamma 2.2.
- **Slider:** it's relative-drag (it doesn't jump to where you touch), so you can fine-tune a level.
  Several phones stay in sync after each change.
- **Wi-Fi power saving is off** for low latency (~15–20 ms round trip).
- At power-up the light fades in to the last saved setting. Settings are written to flash 3 s after the last change.
- If the program crashes, the Pico reboots after 5 s. Errors are written to `net.log`.

### Wi-Fi robustness

- `config.NETWORKS` is tried in order: `wlan2` (FRITZ!Box, hidden SSID) first, `wlan` (Archer AX10)
  as fallback. Each attempt restarts the Wi-Fi chip.
- **Self-check:** every 30 s the Pico opens a TCP connection to the router (port 80). After 3 failures
  in a row (re-checked every 5 s) it reconnects. This catches the state from
  [`wifi-connection-issue.md`](wifi-connection-issue.md), where the Pico still counts as connected
  but unicast frames no longer arrive. Detection plus reconnect takes about a minute.
- Everything is logged to `net.log` with the time synced from the FRITZ!Box.

## Settings worth knowing

| Where | Setting | Default |
|---|---|---|
| `light.py` | `MAX_LEVEL`: brightness cap (slider 100 % → this) | `0.93` (~85 % power) |
| `light.py` | `SLIDE_TAU_MS`, `TOGGLE_MS`: smoothing / on-off fade | `40`, `400` |
| `config.py` | `NETWORKS`: Wi-Fi networks, tried in order | `wlan2`, then `wlan` |
| `config.py` | `COUNTRY`: Wi-Fi regulatory country (`"XX"` would only allow channels 1–11) | `"CH"` (channels 1–13) |
| `bridge.py` | timing (`POL_HZ`, `DEAD_US`) | 1 kHz, 30 µs |

## Safety rules (from the hardware notes)

1. GP0 and GP1 must never be high at the same time (shoot-through). The PIO program makes this impossible.
   A crash in the Python/web code can't violate it.
2. Dead time ≥ 30 µs; the maximum pulse is clamped so it can't shrink.
3. After **any** change to timing in `bridge.py`, test first **without the strip** at a low current limit:
   the supply should draw only a few mA.
4. Never connect a 5 V signal from the board (old button pull-ups, PT1 sensor, 78L05 rail) to a Pico pin.
5. Keep Pico GND tied to V−.

## Caveats

- **No login.** Anyone on the Wi-Fi can control the light. Don't expose it to the internet.
- **Address:** the FRITZ!Box always gives the Pico `.38` and resolves `lightstrip.fritz.box` for every
  device that uses it as DNS (all devices on `wlan`/`wlan2`). `lightstrip.local` (mDNS) works on the
  laptop but not reliably on Android phones.
- The dimmest few percent of the slider may look uneven (see To do).

## To do

- [ ] **Dark-end calibration:** add a raw pulse-length test, find the shortest clean pulse (`MIN_ON`) on the scope
  (Math CH1−CH2 reaches full 24 V with a flat top, both polarities glow evenly), then map slider 1 % → `MIN_ON`.
  If still steppy: dither between n and n+1 cycles; pulse skipping only if even dimmer is needed (flicker risk).
- [ ] Delete the old `test.py` from the Pico (contains credentials for another network).
- [ ] Optional: reuse buttons S1/S2 and the PT1 sensor (check for 5 V pull-ups first).
