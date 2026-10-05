# Light strip controller: Wi-Fi + web UI + smooth fading
import asyncio
import network
import sys
import time
import machine
from machine import Pin
import bridge
import config
from light import Light
from web import Server

led = Pin("LED", Pin.OUT)   # on-board LED: on while Wi-Fi is connecting


async def wifi():
    network.country(config.COUNTRY)
    network.hostname(config.HOSTNAME)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(pm=network.WLAN.PM_NONE)   # no power saving: much lower latency
    while True:
        if not wlan.isconnected():
            led.on()
            print("connecting to", config.SSID)
            wlan.disconnect()
            wlan.connect(config.SSID, config.PASSWORD)
            for _ in range(20):
                if wlan.isconnected():
                    break
                await asyncio.sleep(1)
            if wlan.isconnected():
                led.off()
                print("ready: http://%s/  or  http://%s.local/" % (wlan.ifconfig()[0], config.HOSTNAME))
        await asyncio.sleep(5)


async def main():
    light = Light()
    asyncio.create_task(light.run())   # light works even before/without Wi-Fi
    asyncio.create_task(wifi())
    await Server(light).start(80)
    while True:
        await asyncio.sleep(3600)


try:
    asyncio.run(main())
except KeyboardInterrupt:              # stopped from Thonny/mpremote
    bridge.off()
except Exception as e:                 # unexpected crash: reboot (state is restored from flash)
    sys.print_exception(e)
    bridge.off()
    time.sleep(5)
    machine.reset()
