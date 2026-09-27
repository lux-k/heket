#MediaMTX  (docker container to broadcast an audio device to rtsp)
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
from urllib.parse import urlsplit, parse_qs
import requests
import json
import threading
from flask import Flask, send_file, send_from_directory, request, redirect, url_for, flash, get_flashed_messages, session, Response
import math

# ==== CONFIG ====
import heket_config
import heket_common
import heket_classifier

heket_common.migrate_versions()

import turtlepond.dates

with open(os.path.join(heket_config.DATA_DIR, "heket.pid"), "w") as f:
    f.write(str(os.getpid()))

reload_flag = False

def handle_reload(signum, frame):
    global reload_flag
    reload_flag = True

signal.signal(signal.SIGUSR1, handle_reload)

weather = None

AUDIO_CHECK = 50

# ==== DB SETUP ====
os.makedirs(heket_config.DATA_DIR, exist_ok=True)

heket_common.db_setup()

conn = heket_common.get_db()
cur = conn.cursor()

bouts = {}

# ==== LOAD MODEL ====
model = heket_classifier.load_model_from_file(heket_config.MODEL_FILE)

def register_model(model):
    if model.meta_data is not None and "uuid" in model.meta_data:
        cur.execute("select model_id from models where global_id = ?", [model.meta_data["uuid"]])
        row = cur.fetchone()
        if row is None:
            cur.execute("insert into models (global_id, parameters, added_ts) values (?,?,?)", [model.meta_data["uuid"],json.dumps(model.meta_data),turtlepond.dates.get_epoch()])
            conn.commit()
            return cur.lastrowid
        else:
            return row[0]
    else:
        return None

MODEL_ID = register_model(model)

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
            weather["id"] = None
            
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

def load_audio(file):
    global AUDIO_CHECK
    y, sr = librosa.load(file, sr=heket_config.SAMPLE_RATE)
    AUDIO_CHECK += 1
    if AUDIO_CHECK >= 50:
        if np.mean(np.abs(y)) < 0.001:
            heket_config.save_alert("⚠️ Audio likely missing or silent")
        AUDIO_CHECK = 0

    return y, sr

def process_file(path):
    global weather
    global MODEL_ID
    try:
        #this is the complete audio segment
        y, sr = load_audio(path)

        slice_samples = round(model.slice_time * sr)
        segment_samples = round(heket_config.SEGMENT_TIME * sr)

        results = []

        for start_sample in range(0, segment_samples, slice_samples):
            end_sample = start_sample + slice_samples
            audio_slice = y[start_sample:end_sample]

            features = model.extract_features_from_audio(audio_slice, sr)
            prediction, confidence = model.predict(features)

            results.append({
                "offset": start_sample / sr,
                "duration": model.slice_time,
                "prediction": prediction,
                "confidence": confidence
            })


        #TODO: remove this when the columns go
        prediction = results[0]["prediction"]
        confidence = results[0]["confidence"]

        if True:
            weather_id = None
            if weather is not None:
                weather_id = weather["id"]

            #cur.execute("""INSERT INTO detections (recorded, processed, species, confidence, file, weather_id, bout_id) VALUES (?, ?, ?, ?, ?, ?,?)""", [ts_from_filename(path).isoformat(), datetime.now().isoformat(), species, confidence, os.path.basename(path), weather_id, bout_id])
            cur.execute("""INSERT INTO detections (recorded_ts, processed_ts, species, confidence, file, weather_id, duration, sample_rate, model_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         [turtlepond.dates.datetime_to_epoch(ts_from_filename(path)), turtlepond.dates.get_epoch(), prediction, confidence, os.path.basename(path), weather_id, round(librosa.get_duration(y=y, sr=sr),2), sr, MODEL_ID])

            detection_id = cur.lastrowid
            bout_id = bout_get(label=prediction,detection_id=detection_id)

            for res in results:
                cur.execute("""INSERT INTO detection_slices (detection_id, offset, duration, prediction, confidence, bout_id) VALUES (?, ?, ?, ?, ?,?)""",
                            [detection_id, res["offset"], res["duration"], res["prediction"], res["confidence"], bout_id])                
                bout_notate(label=res["prediction"],confidence=res["confidence"],detection_id=detection_id)

            conn.commit()

            notify_web(topic="soundscape", data={"label": prediction, "confidence": confidence, "detection_id": detection_id})
#            notify_web(topic="notification", data={"message": "This is a test message"})
            
            heket_common.move_file(path, os.path.join(heket_config.OUT_DIR, os.path.basename(path)))
        else:
           heket_common.delete_file(path)

        print(f"{path} | {prediction} ({confidence:.2f})")

    except Exception as e:
        print(f"Error processing {path}: {e}")
        
        heket_common.delete_file(path)

def cache_targets():
    cur.execute("""select label_name from class_metadata where target = ?""",[1])
    rows = cur.fetchall()

    results = []
    for r in rows:
        results.append(r[0])

    return results

def bout_get(label, detection_id):
    global bouts
    global TARGET_LABELS

    if not label in TARGET_LABELS:
        #not a target, no bout
        return None
    else:
        # its a frog.. see if a bout exists
        # close if necessary
        bout_close(label)
            
        if label in bouts:
            bout_increment(label, detection_id)
            return bouts[label]["bout_id"] #may be none or a number
        else:
            #new bout completely
            #bouts[species] = {"start_id": None, "start_time": datetime.now().isoformat(), "detections": 0, "last_time": time.time(), "bout_id": None, "end_time": datetime.now().isoformat(), "conf_min": None, "conf_max": None, "conf_total": 0}
            bouts[label] = {"start_id": None, "start_time": turtlepond.dates.get_epoch(), "detections": 0, "last_time": time.time(), "bout_id": None,
                               "end_time": turtlepond.dates.get_epoch(), "conf_min": None, "conf_max": None, "conf_total": 0, "last_id": 0, "clips": 0}
            bout_increment(label, detection_id)
        
        return bouts[label]["bout_id"]

def bout_increment(label, detection_id):
    global bouts

    if label in bouts: #don't have to check the time because it would've been closed already
        #if bouts[label]["
        if bouts[label]["last_id"] != detection_id:
            bouts[label]["last_id"] = detection_id
            bouts[label]["detections"] += 1
            if bouts[label]["bout_id"] is None and bouts[label]["detections"] >= heket_config.BOUT_MIN_CLIPS:
                bout_open(label)

def bout_notify(msg):
    if heket_config.NOTIFICATION_PROVIDER is not None and len(heket_config.NOTIFICATION_PROVIDER) > 0:
        o = urlsplit(heket_config.NOTIFICATION_PROVIDER)
        if o.scheme == "pushover":
            conf = parse_qs(o.netloc)
            if "url" not in conf:
                conf["url"] = "https://api.pushover.net/1/messages.json"
            try:
                params = {"token": conf["token"], "user": conf["user"], "message": msg}
                r = requests.post(conf["url"], json=params)
                print("posted " + msg + " to pushover")
            except Exception as e:
                print("posting to pushover failed - " + str(e))
    
def bout_open(label):
    global bouts
    print(label, "calling bout has begun")
    bout_notify("🐸 " + label + " calling bout started")
    cur.execute("""INSERT INTO bouts (label, start_detection_id, start_ts) values (?,?,?)""", [label, bouts[label]["start_id"], bouts[label]["start_time"]])
    bouts[label]["bout_id"] = cur.lastrowid
    
    #back fill the first couple detections that had an empty bout id
    cur.execute("""update detection_slices set bout_id = ? where prediction = ? and id >= ? and id <= ? and bout_id is null""", [bouts[label]["bout_id"], label, bouts[label]["start_id"], bouts[label]["last_id"]])
    
    conn.commit()

def bout_clean_orphan():
    # clean up dangling bouts

    cur.execute("""select bout_id from bouts where end_detection_id is null""")
    rows = cur.fetchall()
    count = 0
    for row in rows:
        #we have the bout_id of a dangling bout now
        cur.execute("""select max(d.id), max(d.recorded_ts), min(ds.confidence), max(ds.confidence), avg(ds.confidence), count(distinct d.id), ds.bout_id from 
            detections d join detection_slices ds where ds.bout_id = ?""", [ row[0] ])
        vals = cur.fetchall()
        if len(vals) > 0:
            cur.execute("""update bouts set end_detection_id = ?, end_ts = ?, conf_min = ?, conf_max = ?, conf_avg = ?, clips = ? where bout_id = ?""", vals[0])
            count += 1
    
    conn.commit()
    print("Cleaned up", count, "dangling bouts")
    
def bout_close(label, force=False):
    global bouts
    
    # if its in there AND it has gone silent...
    if label in bouts and (force or (bouts[label]["last_time"] + heket_config.BOUT_MAX_SILENT) <= time.time()):
        #save the bout info if present
        if bouts[label]["bout_id"] is not None:
            print(label, "calling bout has ended")
            cur.execute("""update bouts set end_detection_id = ?, end_ts = ?, conf_min = ?, conf_max = ?, conf_avg = ?, clips = ? where bout_id = ?""",
                [bouts[label]["last_id"], bouts[label]["end_time"], bouts[label]["conf_min"], bouts[label]["conf_max"], bouts[label]["conf_avg"], bouts[label]["detections"], bouts[label]["bout_id"]])
            conn.commit()
        
        #regardless zero out the old bout
        del bouts[label]

def bout_notate(label, confidence, detection_id):
    global bouts
    
    if label in bouts:
        if bouts[label]["start_id"] is None:
            bouts[label]["start_id"] = detection_id
        
        bouts[label]["last_id"] = detection_id
        bouts[label]["end_time"] = turtlepond.dates.get_epoch()
        bouts[label]["last_time"] = time.time()
        
        if bouts[label]["conf_min"] is None or confidence < bouts[label]["conf_min"]:
            bouts[label]["conf_min"] = confidence
        
        if bouts[label]["conf_max"] is None or confidence > bouts[label]["conf_max"]:
            bouts[label]["conf_max"] = confidence

        bouts[label]["conf_total"] += confidence
        bouts[label]["clips"] += 1
        bouts[label]["conf_avg"] = bouts[label]["conf_total"] / bouts[label]["clips"]

def notify_web(topic, data):
    try:
        response = requests.post('http://localhost:5000/classifier_message', json={'topic': topic, 'data': data})
    except Exception as e:
        print(f"Error sending notification to web: {e}")

# obsolete
def soundscape_update(label,confidence):
    if False:
        dest = heket_config.CURRENT_STATE
        tmp = dest + ".tmp"
        
        with open(tmp, "w") as f:
            json.dump({"label": label, "confidence": confidence}, f)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp, dest)    

def ts_from_filename(path):
    fname = os.path.basename(path)

    return datetime.strptime(fname, heket_config.FILE_FORMAT).replace(tzinfo=turtlepond.dates.HOST_TZ)

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
        "gunicorn"
    ])

def do_maintenance():
    global bouts
    print("Time to do maintenance")
    cutoff = datetime.now() - timedelta(days = 3)
    search = int(cutoff.timestamp())
    print("Candidates to delete are", cutoff.isoformat()[:16])

    cur = conn.cursor()
    
    # find the closet record.. bear in mind.. if the pipeline is run sporadically, this might fail..
    #cur.execute(f"""select id, recorded from detections where recorded like ?""", [f"{search}%"])
    cur.execute(f"""select min(id) from detections where recorded_ts > ? and recorded_ts < ?""", [search - 60, search + 60])

    rows = cur.fetchall()
    if len(rows) > 0:
        detection_id = rows[0][0]
        buff = 50 #keeps 50 clips around any review events

        # select records to delete if:
        #   they are old enough
        #   they are unlabeled
        #   they are non frogs OR they are very low confidence frogs
        cur.execute(f"""SELECT d.id, d.file FROM detections d  WHERE d.id <= ?
            AND NOT EXISTS (
                SELECT 1 FROM detection_slices ds LEFT JOIN class_metadata cmd ON COALESCE(ds.labeled, ds.prediction) = cmd.label_name
                WHERE ds.detection_id = d.id AND 
                (ds.labeled is not null or (cmd.target = 1 and ds.confidence >= ?))
            )
            AND NOT EXISTS ( SELECT 1 FROM reviews r WHERE
            d.id BETWEEN r.detection_id - {buff}  AND r.detection_id + {buff})""", [detection_id, heket_config.CONF_STRONG])
        rows = cur.fetchall()
        print("Deleting", len(rows), "old files")
        for r in rows:
            #delete all the files
            heket_common.delete_file(os.path.join(heket_config.OUT_DIR, r[1]))
            cur.execute("delete from detection_slices where detection_id = ?", [r[0]])
            cur.execute("delete from detections where id = ?", [r[0]])

        cur.execute("DELETE FROM weather WHERE weather_id NOT IN ( SELECT DISTINCT weather_id FROM detections )")
        conn.commit()

        for label in list(bouts):
            bout_close(label=label)
# ==== MAIN LOOP ====
def main():
    global reload_flag
    global weather
    sleep_time = 8
    maintenance_offset = 3600
    maintenance_time = 0
    last_file = time.time()
    quiet_seconds = 20
    bout_clean_orphan()
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
            for label in list(bouts):
                bout_close(label=label,force=True)

            if ffmpeg is not None:
                ffmpeg.terminate()
            web.terminate()
            break

TARGET_LABELS = cache_targets()

app = None
app = Flask(__name__)
app.secret_key = "super secret key"

def api_control():
    global app
    app.run(host="127.0.0.1", port=4999, threaded=True)

@app.route("/reload_config", methods=["POST"])
def api_reload_config():
    return json.dumps(do_api_call("reload_config"))

@app.route("/reload_targets", methods=["POST"])
def api_reload_targets():
    return json.dumps(do_api_call("reload_targets"))

def do_api_call(command, opts={}):
    ok = True
    msg = None
    global TARGET_LABELS

    try:
        if command == "reload_config":
            handle_reload(None,None)
            msg = "Configuration reloaded"
        elif command == "reload_targets":
            print("Reloading targets")
            TARGET_LABELS = cache_targets()            
    except Exception as e:
        ok = False
        msg = "Command failed"
    
    return {"success": ok, "message": msg}
    
threading.Thread(target=api_control, daemon=True).start()

if __name__ == "__main__":
    main()