#!/usr/bin/env python3
"""Update the Pico over Wi-Fi (talks to ota.py on port 8080).

  python3 push.py light.py index.html   upload files; reboots if a .py file changed
  python3 push.py --log                 show the Pico's connection/error log
  python3 push.py --ls                  list files on the Pico
  python3 push.py --get state.json      print a file from the Pico
  python3 push.py --reboot              restart the Pico

The token comes from OTA_TOKEN in config.py. Set PICO=<ip> to use another address.
"""
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("PICO", "192.168.178.38")
RISKY = {"main.py", "ota.py", "config.py"}   # a mistake here can break OTA itself


def token():
    cfg = {}
    with open(os.path.join(HERE, "config.py")) as f:
        exec(f.read(), cfg)
    return cfg["OTA_TOKEN"]


def call(method, path, data=None, timeout=10):
    req = urllib.request.Request("http://%s:8080%s" % (HOST, path), data=data, method=method,
                                 headers={"X-Token": token()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        sys.exit("%s %s failed (%d): %s" % (method, path, e.code, e.read().decode(errors="replace").strip()))
    except OSError as e:
        sys.exit("can't reach the Pico at %s:8080 (%s)" % (HOST, e))


def wait_until_up():
    t0 = time.time()
    time.sleep(3)
    while time.time() - t0 < 90:
        try:
            urllib.request.urlopen("http://%s/" % HOST, timeout=2).read()
            print("back up after %.0f s" % (time.time() - t0))
            return
        except OSError:
            time.sleep(1)
    print("not back after 90 s; check  python3 push.py --log  or USB")


def main(args):
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
    elif args[0] == "--log":
        print(call("GET", "/file/net.log"), end="")
    elif args[0] == "--ls":
        print(call("GET", "/files"), end="")
    elif args[0] == "--get":
        print(call("GET", "/file/" + args[1]), end="")
    elif args[0] == "--reboot":
        print(call("POST", "/reboot"), end="")
        wait_until_up()
    else:
        risky = [f for f in args if os.path.basename(f) in RISKY]
        if risky and input("%s can break updates over Wi-Fi if wrong. Continue? [y/N] "
                           % ", ".join(risky)).lower() != "y":
            return
        for f in args:
            with open(f, "rb") as fh:
                print(call("PUT", "/file/" + os.path.basename(f), fh.read()), end="")
        if any(f.endswith(".py") for f in args):
            print(call("POST", "/reboot"), end="")
            wait_until_up()
        else:
            print("no reboot needed (index.html is read fresh on every page load)")


main(sys.argv[1:])
