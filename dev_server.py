# Local preview of the web UI (runs on the laptop, no Pico needed).
# Uses the real web.py with a fake light; index.html is re-read on every page load,
# so edit it and just refresh.   python3 dev_server.py [port]   (default 8000)
import asyncio
import socket
import sys
from web import Server


class FakeLight:
    def __init__(self):
        self.level, self.on = 0.5, True

    def state(self):
        return {"b": round(self.level, 4), "on": self.on}

    def set_level(self, b):
        self.level = min(1.0, max(0.0, b)) if b == b else 0.0
        self.on = self.level > 0
        print("level %3.0f%%" % (self.level * 100), end="\r", flush=True)

    def set_on(self, on):
        if on and self.level < 0.01:
            self.level = 0.5
        self.on = on
        print("\non" if on else "\noff", flush=True)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))     # UDP "connect" sends nothing; it just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


async def main(port):
    await Server(FakeLight()).start(port)
    print("preview: http://localhost:%d/   phone: http://%s:%d/" % (port, lan_ip(), port))
    await asyncio.Event().wait()


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000))
