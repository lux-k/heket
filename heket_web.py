from flask import Flask, send_from_directory, request, redirect, url_for, flash, get_flashed_messages
import time
import sqlite3
import heket_config
import heket_common
import os
import shutil
from pathlib import Path
import subprocess
import signal
from datetime import datetime, timedelta
import tempfile
import re
import json
from dotenv import load_dotenv, set_key

LABEL_CANDS = []
CUSTOM_MODELS = []
ALERTS = []
ALERTS_CHECKED = 0
TRAINING = None

def get_db():
    return sqlite3.connect(heket_config.DB_FILE)

def update_labels():
    global LABEL_CANDS
    LABEL_CANDS = sorted([p.name for p in Path(heket_config.LABELED_DIR).iterdir() if p.is_dir()])

def update_models():
    global CUSTOM_MODELS
    
    cm_dir = Path(heket_config.CUSTOM_MODEL_DIR)
    if cm_dir.is_dir():
        CUSTOM_MODELS = sorted([p.name for p in cm_dir.iterdir() if str(p).endswith(".pkl")], reverse=True)
    else:
        CUSTOM_MODELS = []

def check_training():
    global ALERTS_CHECKED
    global TRAINING
    
    if TRAINING is not None and TRAINING.poll() is not None:
        #training finish
        heket_config.save_alert("Model training finished")
        ALERTS_CHECKED = 0
        TRAINING = None
        update_models()    

def update_alerts():
    global ALERTS
    global ALERTS_CHECKED
    
    check_training()
    
    if ALERTS_CHECKED < time.time() + 60:
        ALERTS = heket_config.get_alerts()
        if ALERTS:
            Path(heket_config.ALERT_FILE).unlink(missing_ok=True)
        ALERTS_CHECKED = time.time()
        
update_labels()
update_models()
print("Labels: ", LABEL_CANDS)
print("Models: ", CUSTOM_MODELS)

def ensure_column(conn, table, column, col_type):
    cur = conn.cursor()

    # Get existing columns
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]  # row[1] = column name

    if column not in cols:
        print(f"Adding column {column} to {table}")
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    else:
        print(f"Column {column} already exists")

def db_setup():
    CONN = get_db()
    ensure_column(CONN, "detections", "labeled", "TEXT")
    CONN.cursor().execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        detection_id integer,
        recorded TEXT
    )
    """)
    CONN.commit()
    CONN.close()

db_setup()

app = Flask(__name__)
app.secret_key = "super secret key"

def make_page(title = "Home", content = ""):
    global ALERTS
    update_alerts()
    html = f"<html><head><title>Heket v{heket_config.VERSION}: {title}</title>"
    html += """
<script>
function labelClip(file, label) {
    fetch('/label', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file, label })
    }).then(() => {
        location.reload(); // or remove row dynamically
    });
}
setTimeout(() => {{
    const t = document.getElementById("toast");
    if (t) t.style.display = "none";
}}, 5000);
</script>
<link rel="stylesheet" href="web_assets/style.css">
<link rel="apple-touch-icon" sizes="180x180" href="/web_assets/icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="/web_assets/icons/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/web_assets/icons/favicon-16x16.png">
<link rel="manifest" href="/web_assets/icons/site.webmanifest">
</head><body>
"""    
    messages = get_flashed_messages()
    messages[:0] = ALERTS
  
    if messages:
        html += f"<div id=\"toast\">"
        for m in messages:
            html += f"{m}<br>"
        html += "</div>"
        
    html += "<div class=\"floater\"><form method=\"GET\" action=\"review_add\"><button style=\"height: 60px; background: var(--heket-light-gold); line-height: 1.5;\">&#128056;<br>Frog Calling</button></form></div>"
    url = url_for("index")
    html +="<div style=\"width: 100%; margin-bottom: 20px; text-align: center;\">"
    html += f"<a href=\"{ url }\"><img src=\"/web_assets/heket_logo_small.png\"></a></div><br>"
    html += content
    html += "<br><center><div style=\"width: 100%; margin-bottom: 20px;\">"
    html += f"Heket v{heket_config.VERSION} by <a href=\"mailto:kevin@turtlepond.us\">Kevin Lux</a>; Settings <a href=\"setup\">&#x2699;</a>; Github <a href=\"https://github.com/lux-k/heket\"><img height=\"15\" width=\"15\" src=\"web_assets/github.svg\"></a>; <a href=\"https://turtlepond.us\">TurtlePond.us</a><br>"
    html += "</div></center>"
    html += "</body></html>"
    return html

def make_label_select():
    global LABEL_CANDS
    html = f"<select name=\"label\">"
    html += f"<option></option>"
    for label in LABEL_CANDS:
        html += f"<option>{label}</option>"
    html += "</select> "
    return html
    
def make_label_form(rec = None, file = None, route = None):
    html = "<form method=\"POST\" action=\"/label_apply\">"
    html += f"<audio controls style=\"height:10px;\" src=\"recordings/{file}\"></audio>"
    html += f"<input type=\"hidden\" name=\"rec\" value=\"{rec}\">"
    html += f"<input type=\"hidden\" name=\"file\" value=\"{file}\">"
    
    if route is not None:
        html += f"<input type=\"hidden\" name=\"route\" value=\"{route}\">"
    
    html += make_label_select()
    html += "<button type=\"submit\">Label</button>"
    html += "</form>"
    return html

@app.route("/")
def index():
    if len(heket_config.RTSP_URL) == 0:
        return redirect(url_for("setup"))
    check_training()
    
    conn = get_db()
    cur = conn.cursor()
    
    limit = 5

    cur.execute(f"""
    SELECT id, recorded,
        CASE 
            when labeled is null THEN species
            when labeled is not null then labeled
        END as animal,
    confidence, file
    FROM detections
    WHERE confidence > ? and animal not like ?
    ORDER BY recorded DESC
    LIMIT {limit}
    """,[heket_config.CONF_STRONG, "nonfrog_%"])

    rows = cur.fetchall()
    html = ""
    html += "<div class=\"maingrid\">"

    html += "<div class=\"maincard\">"
    html += "<h1>Strong Frog Detections</h1><ul>"

    for r in rows:
        html += f"<li>{r[1]} — {r[2]} ({r[3]:.2f})"
        html += "<div style=\"display:flex; align-items:center; gap:10px; line-height:1;\">"
        html += make_label_form( rec = r[0], file = r[4] )
        html += "</div>"
        html += "</li><br>"

    html += "</ul>"
    html += "</div>"
    
    html += "<div class=\"maincard\">"
    html += "<h1>Iffy Detections</h1><ul>"

    cur.execute(f"""
    SELECT id, recorded, species, confidence, file
    FROM detections
    WHERE confidence > ? and confidence < ? and labeled is null and file not like \"recording%\"
    ORDER BY confidence asc
    LIMIT {limit}
    """, [heket_config.CONF_IFFY_MIN, heket_config.CONF_IFFY_MAX])

    rows = cur.fetchall()
    for r in rows:
        html += f"<li>{r[1]} — {r[2]} ({r[3]:.2f})"
        html += make_label_form( rec = r[0], file = r[4] )
        html += "</li><br>"

    html += "</ul>"
    html += "</div>"

    html += "<div class=\"maincard\">"
    html += "<h1>Detections by Species</h1><ul>"
    
    cur.execute(f"""
    SELECT 
            CASE 
            when labeled is null THEN species
            when labeled is not null then labeled
        END as animal,
    count(*)
    FROM detections
    WHERE animal not like ?
    GROUP BY animal
    ORDER BY count(*) DESC
    """,["nonfrog_%"])

    rows = cur.fetchall()

    if len(rows) == 0:
        html += f"<li><i>none</i></li>"
    else:
        for r in rows:
            html += f"<li>{r[0]} — {r[1]}</li>"    

    html += "</ul>"
    html += "<h1>Non-Frog Detections</h1><ul>"
    
    cur.execute(f"""
    SELECT 
            CASE 
            when labeled is null THEN species
            when labeled is not null then labeled
        END as animal,
    count(*)
    FROM detections
    WHERE animal like ?
    GROUP BY animal
    ORDER BY count(*) DESC
    """,["nonfrog_%"])

    rows = cur.fetchall()

    if len(rows) == 0:
        html += f"<li><i>none</i></li>"
    else:
        for r in rows:
            html += f"<li>{r[0]} — {r[1]}</li>"    

    html += "</div>"
    html += "<div class=\"maincard\">"

    cur.execute(f"""SELECT id, recorded from reviews order by id desc""")

    rows = cur.fetchall()

    html += "<td valign=\"top\"><h1>Events</h1><ul><h2>Review</h2><ul>"
    if len(rows) == 0:
        html += f"<li><i>none</i></li>"
    else:
        for r in rows:
            html += f"<li><a href=\"review_process?id={r[0]}\">{r[1]}</a></li>"    
    
    html += "</ul></ul><ul><h2>Create</h2>"
    html += "<form method=\"POST\" action=\"review_manual\">Time: <input name=\"time\" placeholder=\"2025-01-01T01:23\"> <button type=\"submit\">Create</button></form>"
    
    html += "</ul></ul>"
    html += "</div>"

    html += "<div class=\"maincard\">"
    html += "<h1>Model</h1>"
    html += f"<ul><h2>Current</h2><ul><span class=\"accent\">{Path(heket_config.MODEL_FILE).name}</span></ul></ul>"
    html += "<ul><h2>Available <form style=\"display: inline;\" method=\"POST\" action=\"model_reload\"><button type=\"submit\">&#10227;</button></form></h2><ul>"
    if len(CUSTOM_MODELS) == 0:
        html += "<i>none</i>"
    else:
        for m in CUSTOM_MODELS:
            html += f"<a href=\"model_switch?model={m}\">{m}</a><br>"
            
    html += "</ul><h2>Train</h2><ul>"
    html += "<form method=\"POST\" action=\"/model_train\"><button type=\"submit\">Train</button></form></ul>"
    html += "</ul>"
    html += "</div>"

    html += "<div class=\"maincard\">"
    html += "<h1>Labels</h1><ul><h2>Add</h2><ul><form method=\"POST\" action=\"/label_add\">New label: <input name=\"label\"> <button type=\"submit\">Add Label</button></form></ul>"
    html += "<h2>Supply</h2><ul><form method=\"POST\" action=\"/label_supply\" enctype=\"multipart/form-data\"><input type=\"file\" name=\"file\"><br>start at <input style=\"width: 40px\" name=\"start\" value=\"0\"> seconds as "
    html += make_label_select() + " <button type=\"submit\">Upload</button></form></ul>"

    html += "<h2>Test</h2><ul><form method=\"POST\" action=\"/label_test\" enctype=\"multipart/form-data\"><input type=\"file\" name=\"file\"><br>"
    html += "start at <input style=\"width: 40px\" name=\"start\" value=\"0\"> seconds <button type=\"submit\">Upload</button></form></ul>"
    
    html += "</ul>"
    html += "</div>"
    html += "</div>"
    conn.close()

    return make_page(title = "Dashboard", content = html)

@app.route("/web_assets/<path:filename>")
def assets(filename):
    return send_from_directory("web_assets", filename)

@app.route("/recordings/<path:filename>")
def files(filename):
    return send_from_directory(heket_config.OUT_DIR, filename)

@app.route("/label_apply", methods=["POST"])
def label():
    rec = request.form["rec"]
    file = request.form["file"]
    label = request.form["label"]
    route = None
    if "route" in request.form:
        route = request.form["route"]

    if len(label) == 0:
        return redirect(url_for("index"))

    print(f"Labeling {rec} as {label}")

    src = Path(os.path.join(heket_config.OUT_DIR, file))
    dst = Path(os.path.join(heket_config.LABELED_DIR, label, file))
    print(f"Copy {src} to {dst}")

    if not dst.exists():
        shutil.copy(src, dst)

    conn = get_db()
    cur = conn.cursor()

    # Get existing columns
    cur.execute("""update detections set labeled = ? where id = ?""", [label, int(rec)])
    conn.commit()
    conn.close()

    flash("Recording labeled")
    if route is None:
        return redirect(url_for("index"))
    else:
        return redirect(route)
	
@app.route("/label_add", methods=["POST"])
def label_add():
    label = request.form["label"]

    if len(label) == 0:
        return redirect(url_for("index"))

    print(f"Adding new label: {label}")
    os.makedirs( os.path.join(heket_config.LABELED_DIR, label), exist_ok=True)

    update_labels()
    
    flash("Label added")
    return redirect(url_for("index"))

@app.route("/label_supply", methods=["POST"])
def label_supply():
    file = request.files["file"]
    label = request.form["label"]
    start = request.form["start"]
    
    if file.filename == '':
        flash("Manual labeling needed file")
        return redirect(url_for("index"))
        
    if len(label) == 0:
        flash("Manual labeling needed label.")
        return redirect(url_for("index"))
    
    if len(start) == 0:
        flash("Manual labeling needed start.")
        return redirect(url_for("index"))

    res = prepare_audio_file(file, start)

    if "trimmed_file" in res and res["trimmed_file"] is not None:
        dst = os.path.join(heket_config.LABELED_DIR, label, Path(res["trimmed_file"]).name)
        print("Moving " + res["trimmed_file"] + " to " + dst)
        heket_common.move_file(res["trimmed_file"], dst)
        flash("Added new sample to " + label)
    else:
        flash("Error producing labeled file")

    return redirect(url_for("index"))

@app.route("/label_test", methods=["POST"])
def label_test():
    file = request.files["file"]
    start = request.form["start"]
    
    if file.filename == '':
        flash("Manual labeling needed file")
        return redirect(url_for("index"))
        
    if len(start) == 0:
        flash("Manual labeling needed start.")
        return redirect(url_for("index"))

    res = prepare_audio_file(file, start)
    if "trimmed_file" in res and res["trimmed_file"] is not None:
        pred_result = None
        try:
            out = subprocess.check_output('python heket_predict.py ' + res["trimmed_file"], shell=True).decode('utf-8').splitlines()[-1]
            pred_result = json.loads(out)
        except Exception as e:
            print(f"Error running predictor: {e}")

        heket_common.delete_file(res["trimmed_file"])
        
        if pred_result is not None:
            flash("Prediction is " + pred_result["prediction"] + " at " + str(pred_result["confidence"]))
        else:
            flash("Error producing prediction")
    else:
        flash("Error producing prediction")
    return redirect(url_for("index"))

def prepare_audio_file(file, start = 0):
    os.makedirs(heket_config.UPLOAD_DIR, exist_ok=True)
    
    new_filename = os.path.join(heket_config.UPLOAD_DIR, "upload_" + datetime.now().strftime("%Y%m%d_%H%M%S") + Path(file.filename).suffix)
    
    print("Uploaded file to", new_filename)
    file.save(new_filename)
    trimmed_file = os.path.join(heket_config.UPLOAD_DIR, "trimmed_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".wav")
    
    ok = False
    try:
        cmd = 'ffmpeg -i ' + new_filename + ' -ss ' + str(start) + ' -t ' + str(heket_config.SEGMENT_TIME) + ' -ac 1 -ar 16000 ' + trimmed_file
        print("Cmd:", cmd)
        subprocess.check_output(cmd, shell=True).decode('utf-8')
        ok = True
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    if ok and Path(trimmed_file).exists:
        print("Created trimmed file", trimmed_file)
    else:
        heket_common.delete_file(trimmed_file)
        trimmed_file = None

    heket_common.delete_file(new_filename)
        
    return {"trimmed_file": trimmed_file}
    
@app.route("/model_reload", methods=["POST"])
def model_reload():
    update_models()
    
    flash("Model list reloaded")
    return redirect(url_for("index"))

@app.route("/model_switch", methods=["GET"])
def model_switch():
    model = request.args["model"]
    
    if len(model) == 0:
        return redirect(url_for("index"))
    
    heket_config.save_config_value("HEKET_MODEL_FILE",os.path.join(heket_config.CUSTOM_MODEL_DIR, model))
    
    signal_pipeline()
    heket_config.reload()

    flash("Model switched")
    return redirect(url_for("index"))

@app.route("/review_add", methods=["GET"])
def review_add():
    html = "<h1>Review Noted</h1><ul>&#9989; Thanks for reporting the frog call."

    conn = get_db()
    cur = conn.cursor()
    cur.execute("select max(id) from detections")
    rows = cur.fetchall()
    detection_id = rows[0][0]
    
    cur.execute("""insert into reviews (detection_id, recorded) values (?,?)""", [detection_id, datetime.now().isoformat()])
    cur.execute("""SELECT last_insert_rowid()""")
    rows = cur.fetchall()
    review_id = rows[0][0]
    conn.commit()
    conn.close()
    
    html += " The review will start at detection Id " + str(rows[0][0]) + ".</ul>"
    html += review_page(review_id)
    return make_page(title = "Review noted", content = html)

def review_page(review_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""select detection_id, recorded from reviews where id = ?""", [review_id])
    rows = cur.fetchall()
    detection_id = rows[0][0]
    
    high = detection_id + int((2 * 60) / heket_config.SEGMENT_TIME)
    low = detection_id - int((5 * 60) / heket_config.SEGMENT_TIME)

    html = f"<h1>Review</h1><ul>Reported: {rows[0][1]}" + str(rows[0][0]) + f"<br>Detection sequence: {detection_id} ({low} &#x2192; {high})<br><br>"

    cur.execute(f"""SELECT id, recorded, species, confidence, file, labeled FROM detections WHERE id >= ? and id <= ? ORDER BY id DESC """, [low,high])
    
    rows = cur.fetchall()
    for r in rows:
        html += f"<li>{r[1]} — {r[2]} ({r[3]:.2f})"
        if r[5] is not None:
            html += f" &#x2192; {r[5]}"
        html += make_label_form( rec = r[0], file = r[4], route = request.full_path )
        html += "</li><br>"
    html += f"<br><form method=\"POST\" action=\"review_delete\"><input type=\"hidden\" name=\"id\" value=\"{review_id}\"><button type=\"submit\">Done with review</button></form>"
    html += "</ul>"
    return html

@app.route("/review_process", methods=["GET"])
def review_process():
    review_id = int(request.args["id"])
    html = review_page(review_id)

    return make_page(title = "Review noted", content = html)

@app.route("/review_delete", methods=["POST"])
def review_delete():
    review_id = int(request.form["id"])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""delete from reviews where id = ?""", [review_id])
    conn.commit()
    conn.close()

    flash("Event deleted")
    return redirect(url_for("index"))

@app.route("/review_manual", methods=["POST"])
def review_manual():
    time = request.form["time"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select id, recorded from detections where recorded like ?""", [f"{time}%"])
    rows = cur.fetchall()
    html = "<h1>Event Creation</h1><ul>"
    if len(rows) > 0:
        detection_id = rows[0][0]
        cur.execute("""insert into reviews (detection_id, recorded) values (?,?)""", [detection_id, rows[0][1]])
        conn.commit()
        html += "&#9989; The event was found and created."
    else:
        html += "&#128683; The database had no recordings at that time. Double check your input."
    
    html += "</ul>"
    
    conn.close()
        
    return make_page(title = "Manual review creation", content = html)
    
@app.route("/setup", methods=["GET"])
def setup():
    html = "<h1>Setup Heket</h1>"
    html += "<ul>"
    html += "<form action=\"setup_save\" method=\"POST\">"
    html += "<table><tr><th>Parameter</th><th>Value</th></tr>"
    html += f"<tr><td>RTSP URL:</td><td><input name=\"RTSP_URL\" size=\"100\" value=\"{heket_config.RTSP_URL}\"></td></tr>"
    html += f"<tr><td>Confidence Strong:</td><td><input name=\"CONF_STRONG\" size=\"5\" value=\"{heket_config.CONF_STRONG}\"></td></tr>"
    html += f"<tr><td>Iffy Min:</td><td><input name=\"CONF_IFFY_MIN\" size=\"5\" value=\"{heket_config.CONF_IFFY_MIN}\"></td></tr>"
    html += f"<tr><td>Iffy Max:</td><td><input name=\"CONF_IFFY_MAX\" size=\"5\" value=\"{heket_config.CONF_IFFY_MAX}\"></td></tr>"
    html += "</table><br>"
    html += "<button type=\"submit\">Save</button>"
    html += "</form>"
    html += "</ul>"

    return make_page(title = "Setup", content = html)

@app.route("/setup_save", methods=["POST"])
def setup_save():
    rtsp_url = request.form["RTSP_URL"]
    conf_strong = request.form["CONF_STRONG"]
    iffy_min = request.form["CONF_IFFY_MIN"]
    iffy_max = request.form["CONF_IFFY_MAX"]
    
    heket_config.save_config_value("HEKET_RTSP_URL",rtsp_url)
    heket_config.save_config_value("HEKET_CONF_STRONG",conf_strong)
    heket_config.save_config_value("HEKET_CONF_IFFY_MIN",iffy_min)
    heket_config.save_config_value("HEKET_CONF_IFFY_MAX",iffy_max)

    signal_pipeline()
    heket_config.reload()

    flash("Configuration saved")
    return redirect(url_for("index"))
    
@app.route("/model_train", methods=["POST"])
def model_train():
    global TRAINING
    if TRAINING is None:
        TRAINING = subprocess.Popen(["python", "heket_train.py"])
        flash("Model training kicked off")
    else:
        flash("Already training a model")
        
    return redirect(url_for("index"))

def signal_pipeline():
    try:
        file = os.path.join(heket_config.DATA_DIR, "heket.pid")
        if Path(file).exists:
            with open(file) as f:
                pid = int(f.read())

            os.kill(pid, 0)  # check if process exists
            os.kill(pid, signal.SIGUSR1)

    except ProcessLookupError:
        print("Heket process not running")    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
	
