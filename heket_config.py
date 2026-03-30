import os
from dotenv import load_dotenv

load_dotenv()

RTSP_URL = os.getenv("HEKET_RTSP_URL","rtsp://admin:password@192.168.100.1:554/h264Preview_01_sub")

DATA_DIR = os.getenv("HEKET_DATA_DIR", "data")
DB_FILE = os.path.join(DATA_DIR, "results.db")
MODEL_FILE = os.path.join("models", "frog_model.pkl")

REC_DIR = os.path.join(DATA_DIR, "recordings")
IN_DIR = os.path.join(REC_DIR, "unprocessed")
OUT_DIR = os.path.join(REC_DIR, "processed")
FILE_FORMAT = "%Y%m%d_%H%M%S.wav"
SEGMENT_TIME = 15
MIN_CONFIDENCE = .2

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
