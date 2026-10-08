import requests
import os
import re
import time
import subprocess
import sqlite3
from datetime import datetime, timedelta
import shutil
import sys
import signal
from urllib.parse import urlsplit, parse_qs
import requests
import json
import threading
import math
from pathlib import Path

# ==== CONFIG ====
import heket_config
import heket_common
import heket_classifier
import heket_audio_source
from guano import GuanoFile

heket_common.migrate_versions()

import turtlepond.dates

reload_flag = False

AUDIO_CHECK = 50

SOURCE_ID = None
SOURCE_CFG = None
SOURCE_PATH = None
END = False
PAM_SOURCES = []

def handle_reload(signum, frame):
    global reload_flag
    reload_flag = True

def shutdown(signum, frame):
    global END
    print("Got shutdown in main")
    END = True

signal.signal(signal.SIGUSR1, handle_reload)
signal.signal(signal.SIGTERM, shutdown)


if len(sys.argv) > 1:
    SOURCE_ID = int(sys.argv[1])

if SOURCE_ID is None:
    print("No source ID given")
    sys.exit(1)

def reload_config():
    global SOURCE_ID
    global SOURCE_CFG
    global SOURCE_PATH
    global reload_flag

    print("Reloading config")

    reload_flag = False

    conn = heket_common.get_db()
    cur = conn.cursor()
    cur.execute("""select config from sources where source_id = ? and enabled = ?""", [SOURCE_ID, 1])
    rows = cur.fetchall()
    if len(rows) == 0:
        print("Source", SOURCE_ID, "doesn't exist or is disabled.")
        SOURCE_CFG = None
        SOURCE_PATH = None
        sys.exit(1)
    else:
        SOURCE_CFG = json.loads(rows[0][0])
        SOURCE_PATH = os.path.join(heket_config.IN_DIR,str(SOURCE_ID))
    
reload_config()

def process_file(path):
    global SOURCE_ID
    try:
        p = Path(path)
        #files may already have a source id on them.. leave it if they do
        #ext may mask as other devices (such as pam devices)
        match = re.match(r"^\d+_\d+_\d+",p.name)
        if match:
            new_file = os.path.join(heket_config.IN_DIR, p.name)
        else:
            new_file = os.path.join(heket_config.IN_DIR, str(SOURCE_ID) + "_" +p.name)
        heket_common.move_file(path, new_file)
    except Exception as e:
        print(f"Error processing acq {path}: {e}")
        heket_common.delete_file(path)

def notify_web(topic, data):
    try:
        response = requests.post('http://localhost:5000/classifier_message', json={'topic': topic, 'data': data})
    except Exception as e:
        print(f"Error sending notification to web: {e}")

# ==== START FFMPEG ====
def start_acq():
    global SOURCE_ID
    global SOURCE_CFG
    global SOURCE_PATH

    os.makedirs(heket_config.IN_DIR, exist_ok=True)
    os.makedirs(SOURCE_PATH, exist_ok=True)

    # the pipeline expects the TS on files to match the server's TZ. so strftime is fine
    # but if the TS comes externally, normalize it to the server's TZ before writing
    if SOURCE_CFG["type"] == "rtsp":
        print("Starting ffmpeg to stream rtsp  for", SOURCE_CFG["name"])
        return subprocess.Popen([
            "ffmpeg", "-nostats",
            "-rtsp_transport", "tcp",
            "-i", SOURCE_CFG["endpoint_url"],
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(SOURCE_CFG["sr"]),
            "-f", "segment",
            "-segment_time", str(SOURCE_CFG["segment_length"]),
            "-reset_timestamps", "1",
            "-strftime", "1", os.path.join(SOURCE_PATH, heket_config.FILE_FORMAT)
        ])
    elif SOURCE_CFG["type"] == "alsa":
        print("Starting arecord for", SOURCE_CFG["name"])
        alsa_addy = heket_audio_source.ALSAAudioSource.physical_path_to_alsa(SOURCE_CFG["hw_addr"])
        print("ALSA address is", alsa_addy)
        if alsa_addy is None:
            return None
        return subprocess.Popen([
            "arecord",
            "-D", alsa_addy,
            "-f", "S16_LE",
            "-r", str(SOURCE_CFG["sr"]),
            "-c", "1",
            "--max-file-time", str(SOURCE_CFG["segment_length"]),
            "--use-strftime",
            os.path.join(SOURCE_PATH, heket_config.FILE_FORMAT)
        ])
    elif SOURCE_CFG["type"] == "ext":
        print("Beginning monitoring for external recordings")
        #most time is spent waiting for udevadm to return something.. 
        #this will rewrite the shutdown handler so interrupts work against the select
        #so you've been warned
        ret_val = heket_audio_source.ExternalAudioSource.monitor_udev(timeout=None,fn=heket_audio_source.ExternalAudioSource.grab_dev,target=SOURCE_CFG["device"])
#        ret_val = "prototype"
        if ret_val is not None:
            notify_web(topic="notification", data={"message": "Detected external storage insertion..."})
            print("Received a device we own:", ret_val)
            mount_path = Path(os.path.join(SOURCE_PATH, "mount"))
#            mount_path = Path("wa")
            os.makedirs(str(mount_path), exist_ok=True)
            work_path = Path(os.path.join(SOURCE_PATH, "work"))
            os.makedirs(str(work_path), exist_ok=True)
            print("Mounting to", str(mount_path))
            mount = subprocess.run(["sudo", "/opt/heket/contrib/heket-mounter.sh", "mount", ret_val, str(SOURCE_ID)], check=True)
            try:
                print("Discovering files...")
                files =  [
                   file.resolve()
                    for file in mount_path.rglob("*")
                    if file.is_file() and file.suffix.lower() == ".wav"
                ]
                print("Found",len(files),"files")
                notify_web(topic="notification", data={"message": f"Found {str(len(files))} files for import"})
                for f in files:
                    gfile = GuanoFile(str(f))
                    if gfile:
                        print(f, "has GUANO")
                        pam = pam_source_get(gfile)
                        print(" ...", pam)
                        is_dupe = pam_check_dupe(file=gfile)
                        print("Dupe", is_dupe)
                        if not is_dupe:
                            subprocess.run(["ffmpeg","-i",str(f),"-f","segment","-segment_time","15","-c","copy",f"{str(work_path)}/slice_%06d.wav"], check=True)
                            converted_dt = gfile["Timestamp"].astimezone(turtlepond.dates.HOST_TZ)
                            for index, path in enumerate(sorted(work_path.glob("slice_*.wav"))):
                                segment_time = converted_dt + timedelta(seconds=index * pam["segment_length"])
                                filename = f"{str(pam['source_id'])}_{segment_time.strftime('%Y%m%d_%H%M%S')}.wav"
                                heket_common.move_file(path, os.path.join(SOURCE_PATH, filename))
                                pam_add_import(pam=pam,source=SOURCE_ID,file=gfile)
#                                break
#                        break
                    else:
                        print(f, "doesnt have GUANO.. skipped")
                notify_web(topic="notification", data={"message": "Completed file import"})
            finally:
                subprocess.run(["sudo", "/opt/heket/contrib/heket-mounter.sh", "umount", str(SOURCE_ID)], check=True)
                pass
        else:
            return None
    else:
        print("Unknown source type", SOURCE_CFG["type"])
        return None

def pam_check_dupe(file):
    conn = heket_common.get_db()
    cur = conn.cursor()
    cur.execute("""select pam_import_id from pam_imports where serial = ? and file_ts = ?""", [file["Serial"], int(file["Timestamp"].astimezone(turtlepond.dates.UTC_TZ).timestamp())])
    rows = cur.fetchall()
    if len(rows) > 0:
        return True
    else:
        return False

def pam_add_import(pam,file,source):
    conn = heket_common.get_db()
    cur = conn.cursor()
    cur.execute("""insert into pam_imports (serial, file_ts, import_ts, ext_id, pam_id) values (?,?,?,?,?)""",
                 [file["Serial"], int(file["Timestamp"].astimezone(turtlepond.dates.UTC_TZ).timestamp()),turtlepond.dates.get_epoch(),source,pam["source_id"]])
    rows = cur.fetchall()
    conn.commit()

def pam_sources_get():
    global PAM_SOURCES
    if len(PAM_SOURCES) > 0:
        return PAM_SOURCES
    
    sources = []

    conn = heket_common.get_db()
    cur = conn.cursor()
    cur.execute("""select config, source_id from sources where type = ? and enabled = ?""", ["pam", 1])
    rows = cur.fetchall()

    for r in rows:
        cfg = json.loads(r[0])
        cfg["source_id"] = r[1]
        sources.append(cfg)

    PAM_SOURCES = sources

    return sources

def pam_source_get(guano):
    sources = pam_sources_get()

    lat, lon = guano["Loc Position"]
    serial = guano["Serial"]
    name = guano["Make"] + " " + guano["Model"] + " " + guano["Serial"]
    for s in sources:
        if s["latitude"] == lat and s["longitude"] == lon and s["serial"] == serial:
            return s

    vals = {"type": "pam", "name": name, "enabled": "on", "latitude": lat, "longitude": lon, "serial": serial, "segment_length": SOURCE_CFG["segment_length"]}
    return pam_source_add(vals)

def pam_source_add(vals):
    global PAM_SOURCES

    conn = heket_common.get_db()
    cur = conn.cursor()
    cur.execute("""insert into sources (type, name, enabled, lat, lon, config, updated_ts) values (?,?,?,?,?,?,?)""",
                  [vals["type"], vals["name"], 1, vals["latitude"], vals["longitude"], json.dumps(vals), turtlepond.dates.get_epoch()])
    source_id = cur.lastrowid
    print("New PAM source", source_id, vals)
    notify_web(topic="notification", data={"message": f"New PAM source '{vals['name']}'"})

    conn.commit()

    PAM_SOURCES = []

    return vals

# ==== MAIN LOOP ====
def main():
    global reload_flag
    global SOURCE_CFG
    global SOURCE_PATH
    global END
    sleep_time = int(SOURCE_CFG["segment_length"] / 2)
    last_file = time.time()
    quiet_seconds = 20
    loop = True

    print("Starting acq...")
    acq = start_acq()

    try:
        while loop and not END:
            files = sorted(os.listdir(SOURCE_PATH))

            for f in files:
                path = os.path.join(SOURCE_PATH, f)

                # skip newest file (still being written)
                if f == files[-1]:
                    continue

                process_file(path)
                last_file = time.time()

            if acq is None:
                if SOURCE_CFG["type"] != "ext":
                    print("No audio source is configured.")
                    heket_config.save_alert("⚠️ No audio source configured")
                acq = start_acq()
            # or if it died
            elif acq.poll() is not None:
                print("acq died, restarting...")
                heket_config.save_alert("⚠️ Audio recording process died")
                acq = start_acq()

            if SOURCE_CFG["type"] != "ext":
                # or if it's hung
                if time.time() > (last_file + quiet_seconds):
                    if acq is not None:
                        heket_config.save_alert("⚠️ No new audio files for 1 minute; restarting audio capture")
                        heket_common.kill_proc(acq)
                        
                        # reset the time to allow 
                        last_file = time.time()

            if reload_flag:
                reload_config()
                
                #if the rtsp stream changed, kill ffmpeg.. let loop restart it
                heket_common.kill_proc(acq)

            time.sleep(sleep_time)
            print("Done with sleep")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        print("Stopping...")
        heket_common.kill_proc(acq)
        loop = False

main()