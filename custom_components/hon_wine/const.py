"""hOn wine cellar constants."""

DOMAIN = "hon_wine"

API_URL = "https://api-iot.he.services"
APP_VERSION = "2.27.9"
OS_VERSION = 31
OS = "android"
DEVICE_MODEL = "exynos9820"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36"
)

WINE_CELLAR = "WC"

# Parameter names per zone, as the cellar reports and the hOn app sends them.
# Entities are only created for the parameters a cellar actually reports, so single-zone
# models work as they are; a model with more zones only needs another entry here.
ZONES = {
    1: {"program": "prCode", "target": "tempSel", "temp": "temp", "humidity": "humidityZ1"},
    2: {"program": "prCodeZ2", "target": "tempSelZ2", "temp": "tempZ2", "humidity": "humidityZ2"},
}
