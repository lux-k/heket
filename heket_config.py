import os
from pathlib import Path
from dotenv import load_dotenv, set_key

VERSION = 0.07

load_dotenv()

DATA_DIR = None

# docker envs default to /data otherwise expect a directory in path
if Path("/.dockerenv").exists():
    DATA_DIR = "/data"
else:
    DATA_DIR = "data"

# you can override the defaults with this env variable
DATA_DIR = os.getenv("HEKET_DATA_DIR", DATA_DIR)
CONFIG_FILE = os.path.join(DATA_DIR, "heket.config")

# these runtime values are reloadable
MODEL_FILE = None
RTSP_URL = None
MODEL_LEVEL = None
SAMPLE_RATE = 0
SEGMENT_TIME = 0

CONF_STRONG = None
CONF_IFFY_MIN = None
CONF_IFFY_MAX = None

# the rest of these values require a restart
DB_FILE = os.path.join(DATA_DIR, "results.db")
CUSTOM_MODEL_DIR = os.path.join(DATA_DIR, "custom_models")
ALERT_FILE = os.path.join(DATA_DIR, "alerts.txt")

REC_DIR = os.getenv("HEKET_REC_DIR", os.path.join(DATA_DIR, "recordings"))
IN_DIR = os.path.join(REC_DIR, "unprocessed")
OUT_DIR = os.path.join(REC_DIR, "processed")
LABELED_DIR = os.path.join(REC_DIR, "labeled")
UPLOAD_DIR = os.path.join(REC_DIR, "uploads")

FILE_FORMAT = "%Y%m%d_%H%M%S.wav"


def reload():
    global CONFIG_FILE
    global MODEL_FILE
    global RTSP_URL
    global MODEL_LEVEL
    global SAMPLE_RATE
    global SEGMENT_TIME

    global CONF_STRONG
    global CONF_IFFY_MIN
    global CONF_IFFY_MAX

    load_dotenv(CONFIG_FILE, override=True)

    MODEL_FILE = os.getenv("HEKET_MODEL_FILE", os.path.join("models", "frog_model.pkl"))
    RTSP_URL = os.getenv("HEKET_RTSP_URL","")
    MODEL_LEVEL = os.getenv("HEKET_MODEL_LEVEL", "simple")
    SAMPLE_RATE = int(os.getenv("HEKET_SAMPLE_RATE", 16000))
    SEGMENT_TIME = int(os.getenv("HEKET_SEGMENT_TIME", 15))

    CONF_STRONG = float(os.getenv("HEKET_CONF_STRONG", 0.3))
    CONF_IFFY_MIN = float(os.getenv("HEKET_CONF_IFFY_MIN", 0.4))
    CONF_IFFY_MAX = float(os.getenv("HEKET_CONF_IFFY_MAX", 0.8))

reload()

print("Heket: Frog Call Listener", VERSION)
print()
print("Data:")
print(f"      DB: {DB_FILE}")
print(f"   Model: {MODEL_FILE}")
print(f"ModelLvl: {MODEL_LEVEL}")
print()
print("Recordings:")
print(f"   RTSP: {RTSP_URL}")
print(f" Format: {FILE_FORMAT}")
print(f"     In: {IN_DIR}")
print(f"    Out: {OUT_DIR}")
print(f"Labeled: {LABELED_DIR}")
print("Confidence:")
print(f"   Strong: {CONF_STRONG}")
print(f" Iffy Min: {CONF_IFFY_MIN}")
print(f" Iffy Max: {CONF_IFFY_MAX}")

def save_config_value(name, value):
    global CONFIG_FILE
    cf = Path(CONFIG_FILE)
    cf.touch(exist_ok=True)

    set_key(dotenv_path=cf, key_to_set=name, value_to_set=value)

def save_alert(msg = ""):
    global ALERT_FILE
    if msg not in get_alerts():
        with open(ALERT_FILE, "a") as f:
            print(msg, file=f)
            print(msg)
    else:
        print("Dupe alert:", msg)

def get_alerts():
    global ALERT_FILE
    ALERTS = []
    if Path(ALERT_FILE).exists():
        with open(ALERT_FILE, "r") as f:
            for line in f:
                l = line.strip()
                if len(l):
                    ALERTS.append(l)
    return ALERTS