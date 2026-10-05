# Tiny web server: serves the page and a WebSocket for live control.
# Hardware-independent (also runs under desktop Python for testing).
import asyncio
import binascii
import hashlib
import json
import os

WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
IDLE_S = 60     # drop a WebSocket after this long without messages (the page sends keepalives)


def _frame(payload, op=1):
    return bytes((0x80 | op, len(payload))) + payload   # our payloads are always < 126 bytes


async def _recv(reader):
    h = await reader.readexactly(2)
    n = h[1] & 0x7F
    if n > 125:
        raise ValueError("frame too big")                # we only expect tiny messages
    mask = await reader.readexactly(4) if h[1] & 0x80 else b"\0\0\0\0"
    data = bytearray(await reader.readexactly(n))
    for i in range(n):
        data[i] ^= mask[i & 3]
    return h[0] & 0x0F, data


class Server:
    def __init__(self, light, page="index.html"):
        self.light = light
        self.page = page
        self.clients = set()

    async def start(self, port=80):
        return await asyncio.start_server(self._handle, "0.0.0.0", port)

    async def _handle(self, reader, writer):
        try:
            parts = (await reader.readline()).decode().split()
            headers = {}
            while True:
                h = await reader.readline()
                if h in (b"\r\n", b"\n", b""):
                    break
                k, _, v = h.decode().partition(":")
                headers[k.strip().lower()] = v.strip()
            path = parts[1].split("?")[0] if len(parts) > 1 else "/"
            if path == "/ws" and headers.get("upgrade", "").lower() == "websocket":
                await self._websocket(reader, writer, headers)
            elif path == "/":
                await self._send_page(writer)
            else:
                writer.write(b"HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
        except Exception as e:
            print("client error:", repr(e))
        finally:
            self.clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _send_page(self, writer):
        size = os.stat(self.page)[6]
        writer.write(("HTTP/1.0 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                      "Cache-Control: no-cache\r\nContent-Length: %d\r\n\r\n" % size).encode())
        with open(self.page, "rb") as f:
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()

    async def _websocket(self, reader, writer, headers):
        key = headers["sec-websocket-key"].encode()
        accept = binascii.b2a_base64(hashlib.sha1(key + WS_GUID).digest())[:-1]
        writer.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                     b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
        await self._send(writer)
        self.clients.add(writer)
        while True:
            try:
                op, data = await asyncio.wait_for(_recv(reader), IDLE_S)
            except asyncio.TimeoutError:
                return
            if op == 8:                                  # close
                writer.write(_frame(b"", 8))
                await writer.drain()
                return
            if op == 9:                                  # ping
                writer.write(_frame(bytes(data), 10))
                await writer.drain()
                continue
            if op != 1:
                continue
            try:
                msg = json.loads(str(data, "utf-8"))
                if "b" in msg:                           # slider: {"b": 0.62} while dragging, + "done" on release
                    self.light.set_level(float(msg["b"]))
                    if msg.get("done"):
                        await self._broadcast(skip=writer)
                elif "on" in msg:                        # button: {"on": true}
                    self.light.set_on(bool(msg["on"]))
                    await self._broadcast()
                # anything else (e.g. {}) is a keepalive
            except (ValueError, TypeError, AttributeError):
                continue

    async def _send(self, writer):
        writer.write(_frame(json.dumps(self.light.state()).encode()))
        await writer.drain()

    async def _broadcast(self, skip=None):
        """Sync other open pages. Only on release/toggle, so it's rare and can't stall dragging."""
        for w in list(self.clients):
            if w is not skip:
                try:
                    await asyncio.wait_for(self._send(w), 1)
                except Exception:
                    self.clients.discard(w)
