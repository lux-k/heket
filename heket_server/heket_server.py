#https://www.inaturalist.org/oauth/app_owner_application
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

parent_dir = str(Path(__file__).resolve().parent.parent)

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import heket_config
import heket_common

SESSIONS = {}
WORDS = ['frog','toad','tadpole','pollywog','treefrog','bullfrog']

os.makedirs(heket_config.DATA_DIR, exist_ok=True)

def get_db():
    return heket_common.get_db()
    sqlite3.connect(heket_config.DB_FILE)

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
<link rel="stylesheet" href="web_assets/style.css">
<link rel="apple-touch-icon" sizes="180x180" href="web_assets/icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="web_assets/icons/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="web_assets/icons/favicon-16x16.png">
<link rel="manifest" href="web_assets/icons/site.webmanifest">
</head><body>
"""    
    messages = get_flashed_messages()
  
    if messages:
        html += f"<div id=\"toast\">"
        for m in messages:
            html += f"{m}<br>"
        html += "</div>"
        
    html +="<div style=\"width: 100%; margin-bottom: 20px; text-align: center;\">"
    html += f"<img src=\"web_assets/heket_logo_small.png\"></div><br>"
    html += content
    html += "<br><center><div style=\"width: 100%; margin-bottom: 20px;\">"
    html += f"Heket v{heket_config.VERSION} by <a href=\"mailto:kevin@turtlepond.us\">Kevin Lux</a>; Github <a href=\"https://github.com/lux-k/heket\"><img height=\"15\" width=\"15\" src=\"web_assets/github.svg\"></a>; <a href=\"https://turtlepond.us\">TurtlePond.us</a><br>"
    html += "</div></center>"
    html += """
"""
    html += "</body></html>"
    return html

@app.route("/web_assets/<path:filename>")
def assets(filename):
    return send_from_directory("../web_assets", filename)

@app.route("/device_register", methods=["POST"])
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
            return jsonify({"challenge": challenge, "status": "pending", "challenge_url": f"{heket_config.TURTLEPOND}device_link"})
        else:
            abort(403)
    else:
        abort(403)

@app.route("/device_link", methods=["GET"])
@app.route("/device_link/<code>", methods=["GET"])
def device_link(code=None):
    if code is not None:
        return link_challenge_confirm(code)
    else:
        html = "<h1>Link Your Device</h1>"
        html += "<ul>Linking your device allows you to use TurtlePond to share your recording with websites such as iNaturalist.<br><br>To complete this process:"
        html += "<ol><li>Go to your Heket web console.<li>Click on the Settings gear at the bottom of the page.<li>Click the Link or Relink button.<li>Copy the displayed code to the box below.</ol>"
        html += "<form method=\"POST\" action=\"device_link_process\">"
        html += "<h2>Enter Your Code</h2><select name=\"word\">"
        global WORDS
        for w in WORDS:
            html += f"<option>{w}</option>"
        html += "</select> &#8212; <input name=\"number\"><br><br><button type=\"submit\">Link</button>"
            
        return make_page(title="Link your Heket device",content=html)
    
@app.route("/device_link_process", methods=["POST"])
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

@app.route("/ping", methods=["GET"])
def ping():
    device_id = auth_device()
    
    return jsonify({"status": "OK"})

@app.route("/session_create", methods=["GET"])
def session_create():
    device_id = auth_device()
    
    global SESSIONS
    sess_id = str(uuid.uuid4())
    SESSIONS[ sess_id ] = {"expires": time.time() + 600, "device_id": device_id}

    return jsonify({"session": sess_id, "url": f"{heket_config.TURTLEPOND}session/{sess_id}"})

@app.route("/session/<path:sess_id>", methods=["GET"])
def session(sess_id):
    global SESSIONS
    
    if sess_id not in SESSIONS or SESSIONS[sess_id]["expires"] < time.time():
        abort(403)
        
    SESSIONS[sess_id]["expires"] = time.time() + 600

    return "Hello! " + str(SESSIONS[sess_id]["device_id"])

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
#CONN.cursor().execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_challenge_unq ON challenges(challenge)""")
CONN.commit()
CONN.close()

maintenance()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
	
