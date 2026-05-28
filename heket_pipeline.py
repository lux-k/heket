import requests
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
import heket_common
import heket_classifier

with open(os.path.join(heket_config.DATA_DIR, "heket.pid"), "w") as f:
    f.write(str(os.getpid()))

reload_flag = False

def handle_reload(signum, frame):
    global reload_flag
    reload_flag = True

signal.signal(signal.SIGUSR1, handle_reload)

# ==== LOAD MODEL ====
model = heket_classifier.load_model_from_file(heket_config.MODEL_FILE)

weather = None

AUDIO_CHECK = 50

# ==== DB SETUP ====
os.makedirs(heket_config.DATA_DIR, exist_ok=True)

heket_common.db_setup()

conn = heket_common.get_db()
cur = conn.cursor()

bouts = {}

def update_weather():
    global weather
    if heket_config.WEATHER_PROVIDER is None or heket_config.WEATHER_PROVIDER == "":
        weather = None
    else:
        if weather is None:
            weather = {}
            
        try:
            weather["last_update"] = int(time.time())
            #configure this as an option, eventually
            weather["update_after"] = weather["last_update"] + 300
            response = requests.get(heket_config.WEATHER_PROVIDER)
            cur_weather = response.json()
            
            cur.execute("""INSERT INTO weather (recorded, temp_c, humidity, pressure_mb, rain_rate_mm) VALUES (?, ?, ?, ?, ?)""",
            [   cur_weather["observations"][0]["obsTimeUtc"],
                cur_weather["observations"][0]["metric"]["temp"],
                cur_weather["observations"][0]["humidity"],
                cur_weather["observations"][0]["metric"]["pressure"],
                cur_weather["observations"][0]["metric"]["precipRate"],
            ])
            weather["id"] = cur.lastrowid
            conn.commit()
            print("Weather updated")
        except Exception as e:
            print(f"An unexpected weather error occurred: {e}")
            weather = None
            
def reload_config():
    global model
    global reload_flag
    global weather

    print("Reloading config")
    m1 = heket_config.MODEL_FILE
    
    heket_config.reload()

    if m1 != heket_config.MODEL_FILE:
        model = heket_classifier.load_model_from_file(heket_config.MODEL_FILE)
        print(f"Changed from model file {m1} to {heket_config.MODEL_FILE}")

    reload_flag = False
    weather = None
    update_weather()
    
reload_config()

# ==== FEATURE EXTRACTION ====
def extract_features(file):
    global AUDIO_CHECK
    y, sr = librosa.load(file, sr=heket_config.SAMPLE_RATE)
    AUDIO_CHECK += 1
    if AUDIO_CHECK >= 50:
        if np.mean(np.abs(y)) < 0.001:
            heket_config.save_alert("⚠️ Audio likely missing or silent")
        AUDIO_CHECK = 0

    return model.extract_features_from_audio(y, sr)

def ts_from_filename(path):
    fname = os.path.basename(path)

    # grab last 15 chars before extension
    ts_part = fname[-19:-4]   # YYYYMMDD_HHMMSS
    return datetime.strptime(fname, heket_config.FILE_FORMAT)

def bout_get(species):
    global bouts
    
    if species.startswith('nonfrog_'):
        #not a target, no bout
        return None
    else:
        # its a frog.. see if a bout exists
        # close if necessary
        bout_close(species)
            
        if species in bouts:
            bout_increment(species)
            return bouts[species]["bout_id"] #may be none or a number
        else:
            #new bout completely
            bouts[species] = {"start_id": None, "start_time": datetime.now().isoformat(), "detections": 0, "last_time": time.time(), "bout_id": None, "end_time": datetime.now().isoformat(), "conf_min": None, "conf_max": None, "conf_total": 0}
            bout_increment(species)
        
        return bouts[species]["bout_id"]

def bout_increment(species):
    global bouts

    if species in bouts: #don't have to check the time because it would've been closed already
        bouts[species]["detections"] += 1
        if bouts[species]["bout_id"] is None and bouts[species]["detections"] >= heket_config.BOUT_MIN_CLIPS:
            bout_open(species)

def bout_open(species):
    global bouts
    print(species, "calling bout has begun")

    cur.execute("""INSERT INTO bouts (species, start_detection_id, start_ts) values (?,?,?)""", [species, bouts[species]["start_id"], bouts[species]["start_time"]])
    bouts[species]["bout_id"] = cur.lastrowid
    
    #back fill the first couple detections that had an empty bout id
    cur.execute("""update detections set bout_id = ? where species = ? and id >= ? and id <= ? and bout_id is null""", [bouts[species]["bout_id"], species, bouts[species]["start_id"], bouts[species]["last_id"]])
    
    conn.commit()

def bout_close(species, force=False):
    global bouts
    
    # if its in there AND it has gone silent...
    if species in bouts and (force or (bouts[species]["last_time"] + heket_config.BOUT_MAX_SILENT) <= time.time()):
        #save the bout info if present
        if bouts[species]["bout_id"] is not None:
            print(species, "calling bout has ended")
            cur.execute("""update bouts set end_detection_id = ?, end_ts = ?, conf_min = ?, conf_max = ?, conf_avg = ?, clips = ? where bout_id = ?""",
                [bouts[species]["last_id"], bouts[species]["end_time"], bouts[species]["conf_min"], bouts[species]["conf_max"], bouts[species]["conf_avg"], bouts[species]["detections"], bouts[species]["bout_id"]])
            conn.commit()
        
        #regardless zero out the old bout
        del bouts[species]

def bout_notate(species, confidence, detection_id):
    global bouts
    
    if species in bouts:
        if bouts[species]["start_id"] is None:
            bouts[species]["start_id"] = detection_id
        
        bouts[species]["last_id"] = detection_id
        bouts[species]["end_time"] = datetime.now().isoformat()
        bouts[species]["last_time"] = time.time()
        
        if bouts[species]["conf_min"] is None or confidence < bouts[species]["conf_min"]:
            bouts[species]["conf_min"] = confidence
        
        if bouts[species]["conf_max"] is None or confidence > bouts[species]["conf_max"]:
            bouts[species]["conf_max"] = confidence

        bouts[species]["conf_total"] += confidence
        
        bouts[species]["conf_avg"] = bouts[species]["conf_total"] / bouts[species]["detections"]

# ==== CLASSIFY + STORE ====
def process_file(path):
    global weather
    try:
        features = extract_features(path)
        species, confidence = model.predict(features)
        #if a nonfrog and it's lower confidence OR it's labeled as a frog above min confidence....
        #if (species.startswith("nonfrog_") and confidence < heket_config.CONF_IFFY_MAX) or confidence > heket_config.CONF_IFFY_MIN:
        if True:
           weather_id = None
           if weather is not None:
               weather_id = weather["id"]
               
           bout_id = bout_get(species=species)
           
           cur.execute("""INSERT INTO detections (recorded, processed, species, confidence, file, weather_id, bout_id) VALUES (?, ?, ?, ?, ?, ?,?)""", [ts_from_filename(path).isoformat(), datetime.now().isoformat(), species, confidence, os.path.basename(path), weather_id, bout_id])
           detection_id = cur.lastrowid
           conn.commit()

           bout_notate(species=species,confidence=confidence,detection_id=detection_id)

           heket_common.move_file(path, os.path.join(heket_config.OUT_DIR, os.path.basename(path)))
        else:
           heket_common.delete_file(path)

        print(f"{path} | {species} ({confidence:.2f})")

    except Exception as e:
        print(f"Error processing {path}: {e}")
        heket_common.delete_file(path)

# ==== START FFMPEG ====
def start_ffmpeg():
    os.makedirs(heket_config.IN_DIR, exist_ok=True)
    os.makedirs(heket_config.OUT_DIR, exist_ok=True)
    os.makedirs(heket_config.LABELED_DIR, exist_ok=True)

    if len(heket_config.RTSP_URL) == 0:
        return None

    return subprocess.Popen([
        "ffmpeg", "-nostats",
        "-rtsp_transport", "tcp",
        "-i", heket_config.RTSP_URL,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(heket_config.SAMPLE_RATE),
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
    global bouts
    print("Time to do maintenance")
    cutoff = datetime.now() - timedelta(days = 3)
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
        print("Deleting", len(rows), "old files")
        for r in rows:
            #delete all the files
            heket_common.delete_file(os.path.join(heket_config.OUT_DIR, r[1]))
            cur.execute("delete from detections where id = ?", [r[0]])
        cur.execute("DELETE FROM weather WHERE weather_id NOT IN ( SELECT DISTINCT weather_id FROM detections )")
        conn.commit()

        for species in list(bouts):
            bout_close(species=species)
# ==== MAIN LOOP ====
def main():
    global reload_flag
    global weather
    sleep_time = 8
    maintenance_offset = 3600
    maintenance_time = 0
    last_file = time.time()
    quiet_seconds = 20
    while True:
        print("Starting ffmpeg...")
        ffmpeg = start_ffmpeg()
        print("Starting web...")
        web = start_web()

        try:
            while True:
                if weather is not None and time.time() > weather["update_after"]:
                    update_weather()
                files = sorted(os.listdir(heket_config.IN_DIR))

                for f in files:
                    path = os.path.join(heket_config.IN_DIR, f)

                    # skip newest file (still being written)
                    if f == files[-1]:
                        continue

                    process_file(path)
                    last_file = time.time()

                # ffmpeg checks
                # first.. unconfigured
                if ffmpeg is None:
                    print("No RTSP source is configured.")
                    heket_config.save_alert("⚠️ No audio source configured")
                    ffmpeg = start_ffmpeg()
                # or if it died
                elif ffmpeg.poll() is not None:
                    print("ffmpeg died, restarting...")
                    heket_config.save_alert("⚠️ Audio recording process died")
                    ffmpeg = start_ffmpeg()

                # or if it's hung
                if time.time() > (last_file + quiet_seconds):
                    if ffmpeg is not None:
                        heket_config.save_alert("⚠️ No new audio files for 1 minute; restarting audio capture")
                        ffmpeg.terminate()

                        try:
                            ffmpeg.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            print("ffmpeg would not terminate cleanly; killing...")
                            ffmpeg.kill()
                            ffmpeg.wait()
                        
                        # reset the time to allow 
                        last_file = time.time()


                # check if web died
                if web.poll() is not None:
                    print("web died, restarting...")
                    heket_config.save_alert("⚠️ Web app failed")
                    web = start_web()

                if reload_flag:
                    rtsp_url = heket_config.RTSP_URL
                    
                    reload_config()
                    
                    #if the rtsp stream changed, kill ffmpeg.. let loop restart it
                    if heket_config.RTSP_URL != rtsp_url:
                        if ffmpeg is not None:
                            ffmpeg.terminate()

                if time.time() > maintenance_time:
                    do_maintenance()
                    maintenance_time = time.time() + maintenance_offset

                time.sleep(sleep_time)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            print("Stopping...")

            #close any bouts before exiting
            for species in list(bouts):
                bout_close(species=species,force=True)

            if ffmpeg is not None:
                ffmpeg.terminate()
            web.terminate()
            break

if __name__ == "__main__":
    main()