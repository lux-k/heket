import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

VERSION = 0.03

RTSP_URL = os.getenv("HEKET_RTSP_URL","rtsp://admin:password@192.168.100.1:554/h264Preview_01_sub")

DATA_DIR = os.getenv("HEKET_DATA_DIR", "data")
DB_FILE = os.path.join(DATA_DIR, "results.db")
MODEL_FILE = os.getenv("HEKET_MODEL_FILE", os.path.join("models", "frog_model.pkl"))

REC_DIR = os.getenv("HEKET_REC_DIR", os.path.join(DATA_DIR, "recordings"))
IN_DIR = os.path.join(REC_DIR, "unprocessed")
OUT_DIR = os.path.join(REC_DIR, "processed")
LABELED_DIR = os.path.join(REC_DIR, "labeled")
CUSTOM_MODEL_DIR = os.path.join(DATA_DIR, "custom_models")

CONF_STRONG = float(os.getenv("HEKET_CONF_STRONG", 0.3))
CONF_IFFY_MIN = float(os.getenv("HEKET_CONF_IFFY_MIN", 0.4))
CONF_IFFY_MAX = float(os.getenv("HEKET_CONF_IFFY_MAX", 0.8))

FILE_FORMAT = "%Y%m%d_%H%M%S.wav"
SEGMENT_TIME = 15

def reload():
    global MODEL_FILE
    global DATA_DIR
    load_dotenv()
    MODEL_FILE = os.getenv("HEKET_MODEL_FILE", MODEL_FILE)
    
    model_file = os.path.join(DATA_DIR, "current_model.txt")
    if Path(model_file).exists():
        print("There is a current model file in the data directory, that overrides everything else.")
        with open(model_file) as f:
            MODEL_FILE = f.read()

reload()

print("Heket: Frog Call Listener")
print()
print("Data:")
print(f"      DB: {DB_FILE}")
print(f"   Model: {MODEL_FILE}")
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

