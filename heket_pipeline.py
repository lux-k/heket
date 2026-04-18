import os
import time
import subprocess
import sqlite3
import librosa
import numpy as np
from datetime import datetime, timedelta
import joblib
import shutil
import sys
import signal

# ==== CONFIG ====
import heket_config

with open(os.path.join(heket_config.DATA_DIR, "heket.pid"), "w") as f:
    f.write(str(os.getpid()))

reload_flag = False

def handle_reload(signum, frame):
    global reload_flag
    reload_flag = True

signal.signal(signal.SIGUSR1, handle_reload)

# ==== LOAD MODEL ====
model = None

def reload_config():
    global model
    global reload_flag
    print("Reloading config")
    print(f"Model was {heket_config.MODEL_FILE}")
    heket_config.reload()
    model = joblib.load(heket_config.MODEL_FILE)
    print(f"Model now {heket_config.MODEL_FILE}")
    reload_flag = False

reload_config()

# ==== DB SETUP ====
os.makedirs(heket_config.DATA_DIR, exist_ok=True)
conn = sqlite3.connect(heket_config.DB_FILE)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded TEXT,
    processed TEXT,
    species TEXT,
    confidence REAL,
    file TEXT,
    labeled TEXT
)
""")
conn.commit()

# ==== FEATURE EXTRACTION ====
def extract_features(file):
    y, sr = librosa.load(file, sr=16000)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    return np.mean(mfcc, axis=1)

def ts_from_filename(path):
    fname = os.path.basename(path)

    # grab last 15 chars before extension
    ts_part = fname[-19:-4]   # YYYYMMDD_HHMMSS
    return datetime.strptime(fname, heket_config.FILE_FORMAT)

def delete_file(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass  # already gone, no big deal
    except Exception as e:
        print(f"Error deleting {path}: {e}")

def move_file(src, dst):
    try:
        shutil.move(src, dst)
    except Exception as e:
        print(f"Error moving {src} → {dst}: {e}")
		
# ==== CLASSIFY + STORE ====
def process_file(path):
    try:
        features = extract_features(path)
        probs = model.predict_proba([features])[0]

        idx = probs.argmax()
        species = model.classes_[idx]
        confidence = float(probs[idx])

        #if a nonfrog and it's lower confidence OR it's labeled as a frog above min confidence....
        #if (species.startswith("nonfrog_") and confidence < heket_config.CONF_IFFY_MAX) or confidence > heket_config.CONF_IFFY_MIN:
        if True:
           cur.execute("""INSERT INTO detections (recorded, processed, species, confidence, file) VALUES (?, ?, ?, ?, ?)""", (ts_from_filename(path).isoformat(), datetime.now().isoformat(), species, confidence, os.path.basename(path)))
           conn.commit()
           move_file(path, os.path.join(heket_config.OUT_DIR, os.path.basename(path)))
        else:
           delete_file(path)

        print(f"{path} | {species} ({confidence:.2f})")

    except Exception as e:
        print(f"Error processing {path}: {e}")
        delete_file(path)

# ==== START FFMPEG ====
def start_ffmpeg():
    os.makedirs(heket_config.IN_DIR, exist_ok=True)
    os.makedirs(heket_config.OUT_DIR, exist_ok=True)
    os.makedirs(heket_config.LABELED_DIR, exist_ok=True)

    return subprocess.Popen([
        "ffmpeg", "-nostats",
        "-rtsp_transport", "tcp",
        "-i", heket_config.RTSP_URL,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-f", "segment",
        "-segment_time", str(heket_config.SEGMENT_TIME),
        "-reset_timestamps", "1",
		"-strftime", "1", os.path.join(heket_config.IN_DIR, heket_config.FILE_FORMAT)
    ])

def start_web():
    return subprocess.Popen([
        "python", "heket_web.py",
    ])

def do_maintenance():
    print("Time to do maintenance")
    cutoff = datetime.now() - timedelta(days = 2)
    search = cutoff.isoformat()[:16]
    print("Candidates to delete are", search)

    cur = conn.cursor()
    
    # find the closet record.. bear in mind.. if the pipeline is run sporadically, this might fail..
    cur.execute(f"""select id, recorded from detections where recorded like ?""", [f"{search}%"])

    rows = cur.fetchall()
    if len(rows) > 0:
        detection_id = rows[0][0]
        buff = 50 #keeps 50 clips around any review events

        # select records to delete if:
        #   they are old enough
        #   they are unlabeled
        #   they are non frogs OR they are very low confidence frogs
        cur.execute(f"""SELECT d.id, d.file FROM detections d WHERE d.id <= ? AND labeled is null and
            (species like ? or confidence < ?) and NOT EXISTS ( SELECT 1 FROM reviews r WHERE
            d.id BETWEEN r.detection_id - {buff} AND r.detection_id + {buff} )""", [detection_id, "nonfrog_%", heket_config.CONF_STRONG])
        rows = cur.fetchall()
        for r in rows:
            #delete all the files
            #delete_file(os.path.join(heket_config.OUT_DIR, r[1]))
            print("Delete " + os.path.join(heket_config.OUT_DIR, r[1]))

#        cur.execute(f"""delete FROM detections d WHERE d.id <= ? AND labeled is null and
#            (species like ? or confidence < ?) and NOT EXISTS ( SELECT 1 FROM reviews r WHERE
#            d.id BETWEEN r.detection_id - {buff} AND r.detection_id + {buff} )""", [detection_id, "nonfrog_%", heket_config.CONF_STRONG])

# ==== MAIN LOOP ====
def main():
    global reload_flag
    sleep_time = 2
    maintenance_offset = 3600
    maintenance_time = 0
    while True:
        print("Starting ffmpeg...")
        ffmpeg = start_ffmpeg()
        print("Starting web...")
        web = start_web()

        try:
            while True:
                files = sorted(os.listdir(heket_config.IN_DIR))

                for f in files:
                    path = os.path.join(heket_config.IN_DIR, f)

                    # skip newest file (still being written)
                    if f == files[-1]:
                        continue

                    process_file(path)

                # check if ffmpeg died
                if ffmpeg.poll() is not None:
                    print("ffmpeg died, restarting...")
                    ffmpeg = start_ffmpeg()

                # check if web died
                if web.poll() is not None:
                    print("web died, restarting...")
                    web = start_web()

                if reload_flag:
                    reload_config()

                if time.time() > maintenance_time:
                    do_maintenance()
                    maintenance_time = time.time() + maintenance_offset

                time.sleep(sleep_time)

        finally:
            print("Stopping...")
            ffmpeg.terminate()
            web.terminate()
            break

if __name__ == "__main__":
    main()