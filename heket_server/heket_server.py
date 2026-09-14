from flask import Flask, send_file, send_from_directory, request, redirect, url_for, flash, get_flashed_messages, session, jsonify, abort
import time
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key
import hashlib
import random
import uuid
import sys
from pathlib import Path
import os
import turtlepond.crypto
import turtlepond.dates
import turtlepond.storage
import soundfile as sf
import json

parent_dir = str(Path(__file__).resolve().parent.parent)

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import heket_config
import heket_common

STORAGE = None

if True:
    key = os.getenv("HEKET_CRYPTO_KEY", "")
    if len(key) == 0:
        key = turtlepond.crypto.Cipher.make_key()
        heket_config.save_config_value("HEKET_CRYPTO_KEY", turtlepond.crypto.Cipher.pack(key))
    else:
        key = turtlepond.crypto.Cipher.unpack(key)

    heket_config.CRYPTO = turtlepond.crypto.Cipher(key)

import heket_inaturalist

def init_storage():
    global STORAGE
    STORAGE_CFG = json.loads(os.getenv("HEKET_STORAGE_CFG", '{"fs": {"base": "' + heket_config.REC_DIR + '"}}'))

    backend = next(iter(STORAGE_CFG))
    STORAGE = turtlepond.storage.create(type=backend, configuration=STORAGE_CFG[backend])

init_storage()

SESSIONS = {}
WORDS = ['frog','toad','tadpole','pollywog','treefrog','bullfrog']

os.makedirs(heket_config.DATA_DIR, exist_ok=True)

def get_db():
    return heket_common.get_db()

heket_common.db_setup()

app = Flask(__name__)
app.secret_key = "super secret key"

def make_challenge():
    global WORDS
    
    challenge = WORDS[ random.randint(0,len(WORDS) - 1) ]
    challenge += "-"
    challenge += f"{random.randint(0,9999):04d}"
    
    return challenge

def key_to_hash(key):
    return hashlib.sha256(key.encode('utf-8')).hexdigest()

def make_page(title = "Home", content = ""):
    html = f"<html><head><title>Heket v{heket_config.VERSION}: {title}</title>"
    html += """
<script>
setTimeout(() => {{
    const t = document.getElementById("toast");
    if (t) t.style.display = "none";
}}, 5000);

</script>
<link rel="stylesheet" href="/web_assets/style.css">
<link rel="apple-touch-icon" sizes="180x180" href="/web_assets/icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="/web_assets/icons/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/web_assets/icons/favicon-16x16.png">
<link rel="manifest" href="/web_assets/icons/site.webmanifest">
</head><body>
"""    
    messages = get_flashed_messages()
  
    if messages:
        html += f"<div id=\"toast\">"
        for m in messages:
            html += f"{m}<br>"
        html += "</div>"
        
    html +="<div style=\"width: 100%; margin-bottom: 20px; text-align: center;\">"
    html += f"<img src=\"/web_assets/heket_logo_small.png\"></div><br>"
    html += content
    html += "<br><center><div style=\"width: 100%; margin-bottom: 20px;\">"
    html += f"Heket v{heket_config.VERSION} by <a href=\"mailto:kevin@turtlepond.us\">Kevin Lux</a>; Github <a href=\"https://github.com/lux-k/heket\"><img height=\"15\" width=\"15\" src=\"/web_assets/github.svg\"></a>; <a href=\"https://turtlepond.us\">TurtlePond.us</a><br>"
    html += "</div></center>"
    html += """
"""
    html += "</body></html>"
    return html

@app.route("/web_assets/<path:filename>")
def assets(filename):
    return send_from_directory("../web_assets", filename)

@app.route("/device/register", methods=["POST"])
def device_register():
    req = request.get_json() 
    #gets the key K from the device
    
    print(req)
    
    k_hashed = key_to_hash(req["device_key"])
    print("Got", k_hashed)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select device_id from devices where device_key_hash = ?""", [k_hashed])
    rows = cur.fetchall()
    if len(rows) == 0:
        # this is a new device key.. give it a challenge code
        cur.execute(f"""insert into devices (device_key_hash,status,created) values (?,?,?)""", [k_hashed,"PENDING",datetime.now().isoformat()])
        device_id = cur.lastrowid
        challenge = make_challenge()
        cur.execute(f"""select device_id from challenges where challenge = ? and expires >= ?""", [challenge, time.time()])
        rows = cur.fetchall()
        if len(rows) == 0:
            cur.execute(f"""insert into challenges (device_id, challenge, expires) values (?,?,?)""", [device_id, challenge, time.time() + 600])
            conn.commit()
            return jsonify({"challenge": challenge, "status": "pending", "challenge_url": f"{heket_config.TURTLEPOND}device/link"})
        else:
            abort(403)
    else:
        abort(403)

@app.route("/api/device/link", methods=["GET"])
@app.route("/device/link", methods=["GET"])
@app.route("/device/link/<code>", methods=["GET"])
def device_link(code=None):
    if code is not None:
        return link_challenge_confirm(code)
    else:
        html = "<h1>Link Your Device</h1>"
        html += "<ul>Linking your device allows you to use TurtlePond to share your recording with websites such as iNaturalist.<br><br>To complete this process:"
        html += "<ol><li>Go to your Heket web console.<li>Click on the Settings gear at the bottom of the page.<li>Click the Link or Relink button.<li>Copy the displayed code to the box below.</ol>"
        html += f"<form method=\"POST\" action=\"/api/{ url_for('device_link_process') }\">"
        html += "<h2>Enter Your Code</h2><select name=\"word\">"
        global WORDS
        for w in WORDS:
            html += f"<option>{w}</option>"
        html += "</select> &#8212; <input name=\"number\"><br><br><button type=\"submit\">Link</button>"
            
        return make_page(title="Link your Heket device",content=html)

@app.route("/device/link/confirm", methods=["POST"])
def device_link_process():
    word = request.form["word"]
    number = request.form["number"]
    
    challenge = word + '-' + number
    
    return link_challenge_confirm(challenge)

def link_challenge_confirm(challenge):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select * from challenges""")
    rows = cur.fetchall()
#    print(rows)

    cur.execute(f"""select device_id from challenges where challenge = ? and expires > ?""", [challenge, time.time()])
    rows = cur.fetchall()
    print(rows)
    if len(rows) == 1:
        cur.execute(f"""update devices set status = ?, linked = ? where device_id = ? and status = ?""", ["LINKED", datetime.now().isoformat(), rows[0][0], "PENDING"])
        cur.execute(f"""delete from challenges where device_id = ?""", [rows[0][0]])
        #link session here
        conn.commit()
        conn.close()
        return make_page(title="Device Linked",content="You have linked your device")
    else:
        flash("Code invalid")
        conn.close()
        return device_link()    

def auth_device():
    auth_header = request.headers.get('X-Heket-ID', None)
    
    if auth_header is None:
        abort(403)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select device_id from devices where device_key_hash = ? and status = ?""", [key_to_hash(auth_header), "LINKED"])
    rows = cur.fetchall()
    conn.close()
    
    if len(rows) == 0:
        abort(403)
    else:
        return rows[0][0]

@app.route("/device/ping", methods=["GET"])
def ping():
    device_id = auth_device()
    
    return {"status": "OK", "capabilities": get_device_caps(device_id)}

def get_device_caps(device_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select provider from external_accounts where device_id = ?""", [device_id])
    rows = cur.fetchall()

    caps = ['turtlepond']

    for r in rows:
        caps.append(r[0].lower())

    return caps

@app.route("/session", methods=["POST"])
def session_create():
    device_id = auth_device()
    
    global SESSIONS
    sess_id = str(uuid.uuid4())
    SESSIONS[ sess_id ] = {"expires": time.time() + 600, "device_id": device_id}

    return jsonify({"session": sess_id, "url": f"{heket_config.TURTLEPOND}session/{sess_id}"})

@app.route("/session/<path:sess_id>", methods=["GET"])
def session_get(sess_id):
    global SESSIONS

    session["id"] = sess_id

    device_id = validate_session()

    html = f"iNaturalist link: "
    if heket_inaturalist.is_device_linked(device_id):
        html += "✅"
    else:
        html += "🚫"

    html += " <form style=\"display: inline\" method=\"POST\" action=\"../link/inaturalist\"><button>Reauthorize</button></form>"
    return make_page(title="Manage Integrations",content=html)

@app.route("/packs", methods=["GET"])
def packs_list():
    device_id = auth_device()

    sample_rate = request.args.get("sample_rate", type=int)
    duration = request.args.get("duration", type=float)

    result = []

    #CONN.cursor().execute("""CREATE TABLE IF NOT EXISTS clip_packs (pack_id integer primary key autoincrement, label text, audio_sr int, duration real, file text, update_ts int)""")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""select pack_id, label, audio_sr, duration from clip_packs where audio_sr = ? and duration = ? order by label""", [sample_rate, duration])
    rows = cur.fetchall()
    for r in rows:
        result.append( {"pack_id": r[0], "label": r[1], "sample_rate": r[2], "duration": r[3]} )

    return result

@app.route("/packs/<packId>", methods=["GET"])
def pack_download(packId):
    device_id = auth_device()

    packId = int(packId)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""select file, label from clip_packs where pack_id = ?""", [packId])
    rows = cur.fetchall()
    if len(rows) != 1:
        abort(400)
    else:
        url = STORAGE.get_url(f"packs/{rows[0][1]}/{rows[0][0]}")
        print(url)

    return {"pack_id": packId, "url": url}

def session_get(sess_id):
    global SESSIONS

    session["id"] = sess_id

    device_id = validate_session()

    html = f"iNaturalist link: "
    if heket_inaturalist.is_device_linked(device_id):
        html += "✅"
    else:
        html += "🚫"

    html += " <form style=\"display: inline\" method=\"POST\" action=\"../link/inaturalist\"><button>Reauthorize</button></form>"
    return make_page(title="Manage Integrations",content=html)

def validate_session():
    global SESSIONS

    if "id" not in session:
        abort(403)

    if session["id"] not in SESSIONS or SESSIONS[session["id"]]["expires"] < time.time():
        abort(403)

    SESSIONS[session["id"]]["expires"] = time.time() + 600

    return SESSIONS[session["id"]]["device_id"]

@app.route("/share/inaturalist", methods=["POST"])
def share_inaturalist():
    device_id = auth_device()

    file = request.files["audio"]
    species = request.form["species"]
    utc_ts = int(request.form["utc_ts"])
    latitude = request.form["latitude"]
    longitude = request.form["longitude"]
    detection_id = int(request.form["detection_id"])

    provider = "inaturalist"

    dupe, id = share_check_dupe(device_id=device_id, detection_id=detection_id, provider=provider)
    if dupe:
        return {"shared": dupe, "id": id}

    ok, response = heket_inaturalist.share_detection(device_id=device_id, species=species,utc_ts=utc_ts,latitude=latitude,longitude=longitude,sound=file)
    #ok, response = True, {'id': 399699165}

    resp = {"shared": ok}
    
    if ok:
        resp["id"] = response["id"]
        share_record(device_id=device_id,detection_id=detection_id,provider=provider,provider_id=resp["id"])

    return resp

@app.route("/share/turtlepond", methods=["POST"])
def share_turtlepond():
    device_id = auth_device()

    file = request.files["audio"]
    file.stream.seek(0, 2)
    file_size = file.stream.tell()
    file.seek(0)

    species = request.form.get("species", None)
    utc_ts = int(request.form["utc_ts"])
    latitude = request.form["latitude"]
    longitude = request.form["longitude"]
    label = request.form["label"]
    detection_id = int(request.form["detection_id"])

    provider = "turtlepond"

    dupe, id = share_check_dupe(device_id=device_id, detection_id=detection_id, provider=provider)
    if dupe:
        return {"shared": dupe, "id": id}

    try:
        ok, contrib_id = turtlepond_process_share(file=file, filesize=file_size, device_id=device_id, species=species, utc_ts=utc_ts, latitude=latitude,longitude= longitude,label=label,detection_id=detection_id)
    except Exception as e:
        print(e)
        abort(400)

    resp = {"shared": ok}
    
    if ok:
        resp["id"] = contrib_id
        share_record(device_id=device_id,detection_id=detection_id,provider=provider,provider_id=contrib_id)

    return resp

def get_contrib_path(file):
    return "contrib/" + file[-3:] + "/" + file

def get_pack_path(file):
    return "packs/" + file

def turtlepond_process_share(file=None, filesize=None, species=None, utc_ts=None, latitude=None, longitude=None,label=None,detection_id=None,device_id=None):
    audio = extract_audio_parameters(file)

    new_file = str(uuid.uuid4())
    STORAGE.put(key=get_contrib_path(new_file),source=file.stream)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""insert into contrib_clips (audio_sr, audio_ch, audio_frames, audio_duration, audio_format, audio_subtype,
                species,recorded_ts,latitude,longitude,label,detection_id,device_id,filename,contrib_ts,filesize) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [audio["sample_rate"],audio["channels"],audio["frames"],audio["duration"],audio["format"],audio["subtype"],
                    species,utc_ts,latitude,longitude,label,detection_id,device_id,new_file,turtlepond.dates.get_epoch(),filesize])
    contrib_id = cur.lastrowid
    conn.commit()
    return True, contrib_id

def extract_audio_parameters(file):
    file.seek(0)
    info = sf.info(file)
    file.seek(0)

    return {
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "duration": info.duration,
        "format": info.format,
        "subtype": info.subtype,
    }    

def share_record(device_id=None, detection_id=None, provider=None, provider_id=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""insert into share_log (device_id, detection_id, provider, provider_id, share_ts) values (?,?,?,?,?)""", [device_id, detection_id, provider, provider_id, turtlepond.dates.get_epoch()])
    conn.commit()
    conn.close()

def share_check_dupe(device_id=None, detection_id=None, provider=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""select provider_id from share_log where device_id = ? and detection_id = ? and provider = ?""", [device_id, detection_id, provider])
    rows = cur.fetchall()
    if len(rows) == 1:
        print("Dupe check found dupe")
        return True, rows[0][0]
    else:
        return False, None

@app.route("/link/inaturalist", methods=["POST"])
def inaturalist_link():
    validate_session()

    code = make_challenge()
    session["inat-code"] = code

    url = heket_inaturalist.INATURALIST_URL + "&state=" + code

    return redirect(url)

@app.route("/oauth/inaturalist/callback", methods=["GET"])
def inaturalist_callback():
    dev_id = validate_session()

    if "inat-code" not in session or session["inat-code"] != request.args["state"]:
        print("State code doesn't match")
        abort(403)

    resp = heket_inaturalist.exchange_oauth_code_for_token(request.args["code"])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("delete from external_accounts where device_id = ? and provider = ?",[dev_id,'iNaturalist'])

    cur.execute("""insert into external_accounts (device_id, provider,access_token,connected) values (?,?,?,?)""", [dev_id,'iNaturalist',heket_config.CRYPTO.encrypt(resp["access_token"]),turtlepond.dates.get_epoch()])
    conn.commit()
    conn.close()

    html = "OAuth flow finished"
    return make_page(title="Manage Integrations",content=html)

def maintenance():
    clean_sessions()
    clean_challenges()

def clean_sessions():
    global SESSION
    for sess in SESSIONS:
        if SESSIONS[sess]["expires"] < time.time():
            del SESSIONS[sess]

def clean_challenges():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(f"""select count(*) from devices""")
    rows = cur.fetchall()
    print("Devices:", rows[0][0])
    cur.execute(f"""select count(*) from challenges""")
    rows = cur.fetchall()
    print("Challenges:", rows[0][0])

    cur.execute(f"""delete from challenges where expires < ?""", [time.time()])
    cur.execute(f"""delete from devices where status = ? and device_id not in (select device_id from challenges)""", ['PENDING'])

    cur.execute(f"""select count(*) from devices""")
    rows = cur.fetchall()
    print("Devices:", rows[0][0])
    cur.execute(f"""select count(*) from challenges""")
    rows = cur.fetchall()
    print("Challenges:", rows[0][0])

    conn.commit()
    conn.close()
    
CONN = get_db()

#CONN.cursor().execute("""drop table if exists devices""")
#CONN.cursor().execute("""drop table if exists challenges""")
CONN.cursor().execute("""CREATE TABLE IF NOT EXISTS devices (device_id integer primary key autoincrement, device_key_hash text, status text, created text, linked text)""")
CONN.cursor().execute("""CREATE TABLE IF NOT EXISTS challenges (challenge_id integer primary key autoincrement, device_id int, challenge text, expires int)""")
CONN.cursor().execute("""CREATE TABLE IF NOT EXISTS external_accounts (external_account_id integer primary key autoincrement, device_id int, provider text, provider_user_id text, provider_user_name text, access_token text, connected int)""")
CONN.cursor().execute("""CREATE TABLE IF NOT EXISTS share_log (share_id integer primary key autoincrement, device_id int, detection_id int, provider text, provider_id text, share_ts int)""")
CONN.cursor().execute("""CREATE TABLE IF NOT EXISTS contrib_clips(contrib_id integer primary key autoincrement, audio_sr int, audio_ch int, audio_frames int, audio_duration real, audio_format text, audio_subtype text,
                    species text,recorded_ts int,latitude real,longitude real,label text,detection_id int,device_id int,filename text,contrib_ts int, filesize int, turtlepond_label text)""")
CONN.cursor().execute("""CREATE TABLE IF NOT EXISTS clip_packs (pack_id integer primary key autoincrement, label text, audio_sr int, duration real, file text, update_ts int)""")
#CONN.cursor().execute("""insert into clip_packs (label, audio_sr,duration,file,update_ts) values('test',16000,15,'test.tar',1)""")
#CONN.cursor().execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_challenge_unq ON challenges(challenge)""")
CONN.commit()
CONN.close()

maintenance()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
	
