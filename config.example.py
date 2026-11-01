# Settings for the light strip controller. Copy to config.py and fill in.
# config.py contains secrets and is ignored by git.
NETWORKS = [                       # tried in this order; hidden SSIDs work too
    ("your-wifi", "your-wifi-password"),
    ("your-other-wifi", "its-password"),   # optional fallback, delete if you have only one
]
HOSTNAME = "lightstrip"   # -> http://lightstrip.local/ (if your phone resolves .local names)
COUNTRY = "XX"            # two-letter country code, e.g. "DE" or "US"; XX = worldwide (channels 1-11 only)
PICO_HOST = "192.168.1.50"   # the Pico's IP (laptop side only: push.py uses it); give it a fixed IP in your router
OTA_TOKEN = "change-me"   # password for updates over Wi-Fi (push.py); e.g. python3 -c "import secrets;print(secrets.token_hex(12))"
