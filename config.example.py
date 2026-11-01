# Settings for the light strip controller. Copy to config.py and fill in.
# config.py contains secrets and is ignored by git.
NETWORKS = [                       # tried in this order
    ("wlan2", "your-wifi-password"),    # FRITZ!Box (hidden SSID)
    ("wlan", "your-wifi-password"),     # Archer AX10 (fallback)
]
HOSTNAME = "lightstrip"   # -> http://lightstrip.local/ (if your phone resolves .local names)
COUNTRY = "XX"            # two-letter country code, e.g. "DE" or "US"; XX = worldwide (channels 1-11 only)
OTA_TOKEN = "change-me"   # password for updates over Wi-Fi (push.py); e.g. python3 -c "import secrets;print(secrets.token_hex(12))"
