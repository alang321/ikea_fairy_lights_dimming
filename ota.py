# Over-the-air updates: a tiny token-protected HTTP server on port 8080.
# Independent of light.py/web.py, so a broken app can still be fixed over Wi-Fi.
# Every request needs the header  X-Token: <config.OTA_TOKEN>   (use push.py on the laptop)
#   GET    /files          list files and sizes
#   GET    /file/<name>    download a file (e.g. net.log)
#   PUT    /file/<name>    upload (needs Content-Length); .py files are syntax-checked before
#                          they replace the old file, so a typo can't brick the Pico
#   DELETE /file/<name>    delete a file
#   POST   /reboot         restart (needed after changing .py files)
import asyncio
import os
import machine

PORT = 8080
_NAME_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
_token = None


async def start(token, port=PORT):
    global _token
    _token = token
    return await asyncio.start_server(_handle, "0.0.0.0", port)


def _ok_name(n):
    return 0 < len(n) <= 40 and n[0] != "." and all(c in _NAME_CHARS for c in n)


async def _receive(reader, name, n):
    if n < 0:
        return 411, b"Content-Length required\n"
    tmp = name + ".tmp"
    with open(tmp, "wb") as f:
        while n > 0:
            chunk = await reader.read(min(n, 1024))
            if not chunk:
                break
            f.write(chunk)
            n -= len(chunk)
    if n:
        os.remove(tmp)
        return 400, b"upload incomplete\n"
    if name.endswith(".py"):
        try:
            with open(tmp) as f:
                compile(f.read(), name, "exec")
        except Exception as e:
            os.remove(tmp)
            return 422, ("rejected, %s: %s\n" % (type(e).__name__, e)).encode()
    try:
        os.remove(name)
    except OSError:
        pass
    os.rename(tmp, name)
    return 200, ("saved %s\n" % name).encode()


async def _reboot():
    await asyncio.sleep_ms(500)        # let the response go out first
    machine.reset()


async def _handle(reader, writer):
    status, body = 500, b""
    try:
        parts = (await reader.readline()).decode().split()
        headers = {}
        while True:
            h = await reader.readline()
            if h in (b"\r\n", b"\n", b""):
                break
            k, _, v = h.decode().partition(":")
            headers[k.strip().lower()] = v.strip()
        method, path = (parts + ["", ""])[:2]
        name = path[6:] if path.startswith("/file/") else None
        if not _token or headers.get("x-token") != _token:
            status, body = 403, b"bad token\n"
        elif method == "GET" and path == "/files":
            names = sorted(os.listdir())
            status, body = 200, "".join("%6d  %s\n" % (os.stat(n)[6], n) for n in names).encode()
        elif name is not None and _ok_name(name):
            if method == "GET":
                with open(name, "rb") as f:
                    status, body = 200, f.read()
            elif method == "PUT":
                status, body = await _receive(reader, name, int(headers.get("content-length", -1)))
            elif method == "DELETE":
                os.remove(name)
                status, body = 200, ("deleted %s\n" % name).encode()
            else:
                status, body = 405, b"method not allowed\n"
        elif method == "POST" and path == "/reboot":
            status, body = 200, b"rebooting\n"
            asyncio.create_task(_reboot())
        else:
            status, body = 404, b"not found\n"
    except OSError as e:
        status, body = 404 if e.args and e.args[0] == 2 else 500, ("%r\n" % e).encode()
    except Exception as e:
        status, body = 500, ("%r\n" % e).encode()
    try:
        writer.write(("HTTP/1.0 %d\r\nContent-Type: text/plain\r\nContent-Length: %d\r\n\r\n"
                      % (status, len(body))).encode())
        writer.write(body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass
