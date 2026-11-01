# Light strip controller: Wi-Fi (with self-check), OTA updates, web UI, smooth fading
import asyncio
import io
import network
import os
import select
import socket
import sys
import time
import machine
from machine import Pin
import config
import ota

led = Pin("LED", Pin.OUT)   # on-board LED: on while Wi-Fi is connecting

LOG = "net.log"             # connects, outages and errors; read it with  python3 push.py --log
LOG_MAX = 16_000            # bytes, then it's rotated to net.log.old
CHECK_S = 30                # how often to check that the router is really reachable
RECHECK_S = 5               # faster re-checks once a check has failed
MAX_FAILS = 3               # failed checks in a row before reconnecting


def log(msg):
    t = time.localtime()
    line = "%04d-%02d-%02d %02d:%02d:%02d UTC  %s" % (t[0], t[1], t[2], t[3], t[4], t[5], msg)
    print(line)
    try:
        if os.stat(LOG)[6] > LOG_MAX:
            os.rename(LOG, LOG + ".old")
    except OSError:
        pass
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def log_exception(where, e):
    buf = io.StringIO()
    sys.print_exception(e, buf)
    log("%s: %s" % (where, buf.getvalue().strip().replace("\n", " | ")))


async def reachable(host, port=80, timeout_ms=5000):
    """True if a TCP connection to host:port succeeds. The router's reply is unicast to the
    Pico, so this catches the "connected, but unicast no longer arrives" state."""
    s = socket.socket()
    try:
        s.setblocking(False)
        try:
            s.connect(socket.getaddrinfo(host, port)[0][-1])
        except OSError as e:
            if e.errno != 115:          # EINPROGRESS is expected for a non-blocking connect
                return False
        poller = select.poll()
        poller.register(s, select.POLLOUT)
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            for _, ev in poller.poll(0):
                return not ev & (select.POLLERR | select.POLLHUP)
            await asyncio.sleep_ms(100)
        return False
    except OSError:
        return False
    finally:
        s.close()


def sync_clock(gateway):
    import ntptime
    for host in (gateway, "pool.ntp.org"):     # the FRITZ!Box is a time server
        try:
            ntptime.host = host
            ntptime.settime()
            return
        except Exception:
            pass


async def join(wlan):
    """Restart the Wi-Fi chip and try the networks in config.NETWORKS in order."""
    for ssid, password in config.NETWORKS:
        led.on()
        wlan.active(False)
        await asyncio.sleep_ms(300)
        wlan.active(True)
        wlan.config(pm=network.WLAN.PM_NONE)   # no power saving: much lower latency
        wlan.connect(ssid, password)
        for _ in range(20):
            await asyncio.sleep(1)
            if wlan.isconnected():
                led.off()
                return ssid
        print("could not join", ssid)
    return None


async def wifi():
    network.country(config.COUNTRY)
    network.hostname(config.HOSTNAME)
    wlan = network.WLAN(network.STA_IF)
    ssid, fails = None, 0
    while True:
        if fails >= MAX_FAILS or not wlan.isconnected():
            if fails >= MAX_FAILS:
                log("router unreachable %d times in a row on %s, reconnecting" % (fails, ssid))
            elif ssid:
                log("lost connection to %s" % ssid)
            ssid, fails = await join(wlan), 0
            if not ssid:
                await asyncio.sleep(10)
                continue
            ip, _, gateway, _ = wlan.ifconfig()
            sync_clock(gateway)
            log("connected to %s as %s (signal %d dBm)  http://%s/" % (ssid, ip, wlan.status("rssi"), ip))
        elif await reachable(wlan.ifconfig()[2]):
            if fails:
                log("router reachable again after %d failed check(s)" % fails)
            fails = 0
        else:
            fails += 1
            if fails >= MAX_FAILS:
                continue
        await asyncio.sleep(RECHECK_S if fails else CHECK_S)


async def start_app():
    from light import Light
    from web import Server
    light = Light()
    asyncio.create_task(light.run())   # light works even before/without Wi-Fi
    await Server(light).start(80)


async def main():
    asyncio.get_event_loop().set_exception_handler(lambda loop, ctx: log_exception("task error", ctx["exception"]))
    await ota.start(config.OTA_TOKEN)  # first and separate: still works if the app is broken
    try:
        await start_app()
    except Exception as e:
        log_exception("app failed to start", e)
    asyncio.create_task(wifi())
    while True:
        await asyncio.sleep(3600)


try:
    asyncio.run(main())
except KeyboardInterrupt:              # stopped from Thonny/mpremote
    import bridge
    bridge.off()
except Exception as e:                 # unexpected crash: reboot (state is restored from flash)
    log_exception("crash", e)
    time.sleep(5)
    machine.reset()
