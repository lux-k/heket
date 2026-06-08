from flask import Flask, send_file, send_from_directory, request, redirect, url_for, flash, get_flashed_messages, session
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
import heket_classifier
import math
from urllib.parse import urlencode
import requests

LABEL_CANDS = []
CUSTOM_MODELS = []
ALERTS = []
ALERTS_CHECKED = 0
TRAINING = None
NAME_CACHE = {}

def get_db():
    return heket_common.get_db()
    sqlite3.connect(heket_config.DB_FILE)

def update_labels():
    global LABEL_CANDS
    LABEL_CANDS = sorted([p.name for p in Path(heket_config.LABELED_DIR).iterdir() if p.is_dir()])

def update_models():
    global CUSTOM_MODELS
    
    cm_dir = Path(heket_config.CUSTOM_MODEL_DIR)
    if cm_dir.is_dir():
        CUSTOM_MODELS = sorted([p.name for p in cm_dir.iterdir() if str(p).endswith(".pkl") or str(p).endswith(".keras")], reverse=True)
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

heket_common.db_setup()

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
<div id="spectrogram-preview">
    <img id="spectrogram-image" onerror="this.onerror=null; this.alt='The graph is not available.'">
</div>
<div id="weather">
</div>
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
    html += """
<script>
const preview = document.getElementById("spectrogram-preview");
const image = document.getElementById("spectrogram-image");
const weather = document.getElementById("weather");
document
.querySelectorAll(".detection-item")
.forEach(row => {
    row.addEventListener("mouseenter", e => {
        const eventId = row.dataset.eventId;
        image.src = "/spectrogram/" + eventId;
        preview.style.display = "block";
        preview.style.left = (e.pageX + 20) + "px";
        preview.style.top = (e.pageY + 30) + "px";
    });

    row.addEventListener("mouseleave", () => {
        preview.style.display = "none";
    });
});

document
.querySelectorAll(".weather-item")
.forEach(row => {
    row.addEventListener("mouseenter", e => {
        const eventId = row.dataset.eventId;
        weather.innerHTML = eventId
        weather.style.display = "block";
        weather.style.left = (e.pageX + 20) + "px";
        weather.style.top = (e.pageY + 30) + "px";
    });

    row.addEventListener("mouseleave", () => {
        weather.style.display = "none";
    });
});

document.querySelectorAll('fieldset legend').forEach(legend => {
  legend.addEventListener('click', () => {
    // Find the closest parent fieldset and toggle the class
    legend.closest('fieldset').classList.toggle('collapsed');
  });
});
</script>
"""
    html += "</body></html>"
    return html

def paginate(url, var, page, max_pages):
    html = ""
    new_dict = dict(request.args)
    
    if var not in new_dict:
        new_dict[var] = 1
        
    html = "Page "
    if page > 1:
        new_dict[var] = page - 1
        html += "<a href=\"" + url_for(url, **new_dict) + "\">&#11207;</a> "
        
    html += f"<form style=\"display: inline\" method=\"GET\" action=\"{url_for(url)}\"><input style=\"width: 50px\" name=\"{var}\" value=\"{page}\">"
    for m in new_dict:
        if m == var:
            continue
        else:
            html += f"<input name=\"{m}\" value=\"{new_dict[m]}\" type=\"hidden\">"
            
    html += "</form> "

    if page < max_pages:
        new_dict[var] = page + 1
        html += "<a href=\"" + url_for(url, **new_dict) + "\">&#11208;</a>"

    session[var] = page

    return html
    
def args_session_default(var, default):
    if var in request.args:
        return request.args.get(var)
    elif var in session:
        return session.get(var)
    else:
        return default

def make_curation_select( current ):
    html = ""
    html += "<select name=\"curated\" onchange=\"this.form.submit()\">"
    html += "<option value=\"\">&#10067;</option>"
    html += "<option value=\"1\""
    if current == 1:
        html += " selected"
    html += ">&#128077;</option>"
    
    html += "<option value=\"0\""
    if current == 0:
        html += " selected"
    html += ">&#128078;</option>"
    html += "</select>"
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
    found = os.path.isfile(os.path.join(heket_config.OUT_DIR, file))
    html = ""
    if found:
        html += f"<form method=\"POST\" action=\"/label_apply\">"
        html += f"<div class=\"detection-item\" data-event-id=\"{rec}\">&#128202;</div>"
        html += f"<audio controls style=\"height:10px;\" src=\"recordings/{file}\"></audio>"
        html += f"<input type=\"hidden\" name=\"rec\" value=\"{rec}\">"
        
        if route is not None:
            html += f"<input type=\"hidden\" name=\"route\" value=\"{route}\">"
        
        html += make_label_select()
        html += "<button type=\"submit\">Label</button>"
        html += "</form>"
    else:
        html += "<br>Recording not found."
    return html

def weather_c_to_f( c ):
    return round((c * 1.8) + 32, 2)    

def weather_mb_to_inhg( mb ):
    return round(mb * 0.02953, 2)

def make_weather(weather):
    html = ""
    #the DB stores metric data
    #html += "&#127777; "
    html += "&nbsp;T "
    if heket_config.WEATHER_UNITS == "imperial":
        #imperial
        html += f"{round(weather_c_to_f(weather['temp_c']),0)}&#176; F"
    else:
        #metric
        html += f"{round(weather['temp_c'],0)}&#176; C"
    
    html += "<br>"
    #html += f"&#128167; {round(weather['humidity'],0)} %<br>"
    html += f"&nbsp;H {round(weather['humidity'],0)} %<br>"
    
    #html += "&nbsp;P "
    html += "&nbsp;P "
    if heket_config.WEATHER_UNITS == "imperial":
        #imperial
        html += f"{weather_mb_to_inhg(weather['pressure_mb'])} inHg"
    else:
        #metric
        html += f"{weather['pressure_mb']} millibars"
    
    html += "<br>"
    if weather["rain_rate_mm"] > 0:
        html += "&#9748; Raining"
    else:
        html += "Not raining"
    return html

def label_to_name( label ):
    global NAME_CACHE
    
    ret_val = None
    if label in NAME_CACHE:
        ret_val = NAME_CACHE[label]
    else:
        conn = get_db()
        cur = conn.cursor()
    
        cur.execute("SELECT common_name from species where label_name = ?", [label])
        rows = cur.fetchall()
        if len(rows) > 0:
            NAME_CACHE[label] = rows[0][0]
            ret_val = rows[0][0]

    if ret_val is None:
        return label
    else:
        return ret_val
        
def make_detection_infoline( id, recorded, animal, confidence, file, labeled, curated, weather, route=None ):
    html = ""
    extra=""
    if route is not None:
        extra="&" + urlencode( {"route": route} )
    html += f"<abbr title=\"Delete detection\"><a href=\"detection_delete?id={id}{extra}\" style=\"color: red\" onclick=\"return confirm('Delete this detection?')\">&#8998;</a></abbr> " #&#9940;
    html += f"{recorded} "
    if weather is not None:
        html += f"<div class=\"weather-item\" data-event-id=\"{make_weather( weather )}\">&#9925;</div>"
    html += f" — { label_to_name(animal) } ({confidence:.2f}) "
    if labeled is not None and labeled != animal:
        html += f"&#x2192; { label_to_name(labeled) } "
    html += f"<form style=\"display: inline\" method=\"POST\" action=\"/curate\">"
    html += f"<input type=\"hidden\" name=\"rec\" value=\"{id}\">"    
    html += make_curation_select(curated) + " "
    if route is not None:
        html += f"<input type=\"hidden\" name=\"route\" value=\"{route}\">"
    html += "</form> "
    if labeled is not None:
        html += "<abbr title=\"Included in training\">&#9989;</abbr> "
    return html

def make_detection( id, recorded, animal, confidence, file, labeled, curated, weather=None, route=None ):
    html = ""
    if weather is not None and weather["temp_c"] is None:
        weather = None
    html += make_detection_infoline( id = id, recorded = recorded, animal = animal, confidence = confidence, file = file, labeled = labeled, curated=curated, weather = weather, route=route )
    html += "<div style=\"display:flex; align-items:center; gap:10px; line-height:1;\">"
    html += make_label_form( rec=id, file=file, route=route )
    html += "</div>"
    return html
    
@app.route("/")
def index():
    if len(heket_config.RTSP_URL) == 0:
        return redirect(url_for("setup"))
    check_training()
    
    conn = get_db()
    cur = conn.cursor()
    
    html = ""
    limit = 5
    
    frog_page = int(args_session_default("fp", 1))
    iffy_page = int(args_session_default("ip", 1))
    bout_page = int(args_session_default("bp", 1))

    cur.execute(f"""
    SELECT count(*), 
        CASE 
            when labeled is null THEN species
            when labeled is not null then labeled
        END as animal    
    FROM detections
    WHERE confidence > ? and animal not like ?
    """,[heket_config.CONF_STRONG, "nonfrog_%"])
    max_page = math.ceil( cur.fetchall()[0][0] / limit )


#            CASE 
#            when labeled is null THEN species
#            when labeled is not null then labeled
#        END as animal,
#        CASE
#            When labeled is null then 0
#            when labeled is not null then 1
#        end as validated
    cur.execute(f"""
    SELECT detections.id, detections.recorded,
        species, confidence, file, labeled, curated, temp_c, humidity, pressure_mb, rain_rate_mm
    FROM detections left join weather on detections.weather_id = weather.weather_id
    WHERE confidence > ? and ((labeled is null and species not like ?) or (labeled is not null and labeled not like ?))
    ORDER BY detections.recorded DESC
    LIMIT ? offset ?
    """,[heket_config.CONF_STRONG, "nonfrog_%", "nonfrog_%", limit, (frog_page - 1) * limit])

    rows = cur.fetchall()
    html += "<div class=\"maingrid\">"

    html += "<div class=\"maincard\">"
    html += "<h1>Strong Detections</h1>"
    html += "<ul>"

    for r in rows:
        html += f"<li>"
        weather = {"temp_c": r[7], "humidity": r[8], "pressure_mb": r[9], "rain_rate_mm": r[10]}
        html += make_detection(id = r[0], recorded = r[1], animal = r[2], confidence = r[3], file = r[4], labeled = r[5], curated = r[6], weather = weather)
        html += "</li>"
        html += "<br>"
    html += "<li style=\"list-style-type: none;\">" + paginate("index", "fp", frog_page, max_page) + "</li>"
    html += "</ul>"
    
    html += "</div>"
    
    html += "<div class=\"maincard\">"
    html += "<h1>Detection Bouts</h1><ul>"
    html += "<h2>Review</h2><ul>"
    cur.execute(f"""
    SELECT count(*)  
    FROM bouts
    """)
    max_page = math.ceil( cur.fetchall()[0][0] / limit )

    cur.execute(f"""
    SELECT bout_id, species, start_ts, end_ts, clips, conf_min, conf_max from bouts order by start_ts desc
    LIMIT ? offset ?
    """, [limit, (bout_page - 1) * limit])

    rows = cur.fetchall()
    if len(rows) == 0:
        html += f"<li><i>none</i><br><br></li>"
    else:
        for r in rows:
            html += f"<li>"
            if r[3] is not None:
                html += f"<abbr title=\"Delete bout\"><a href=\"bout_delete?id={r[0]}\" style=\"color: red\" onclick=\"return confirm('Delete this bout?')\">&#8998;</a></abbr> "
            html += f"<a href=\"bout_review?bout_id={r[0]}\">{label_to_name(r[1])}</a> "
            if r[3] is None:
                html += f"since {r[2][:16]}"
            else:
                html += f"from {r[2][:16]} until {r[3][:16]}"
                if r[5] is not None and r[6] is not None:
                    html += f"<br>{r[4]} detections ranging from {r[5]:.2f} to {r[6]:.2f}"
            html += "</li>"
            html += "<br>"

    html += "<li style=\"list-style-type: none;\">" + paginate("index", "bp", bout_page, max_page) + "</li>"
    html += "</ul>"
    
    html += "<h2>Create</h2><ul>"
    html += "<form method=\"POST\" action=\"bout_create\">Beginning <input name=\"bout_start\" placeholder=\"2025-01-01T01:23\"> until <input name=\"bout_end\" placeholder=\"2025-01-01T01:23\"><br>for species "
    html += make_label_select() + "<button type=\"submit\">Create</button></form>"
    html += "</ul>"

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
            html += f"<li><a href=\"class_review?class={r[0]}\">{label_to_name(r[0])}</a> — {r[1]}</li>"    

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
            html += f"<li><a href=\"class_review?class={r[0]}\">{label_to_name(r[0])}</a> — {r[1]}</li>"    

    html += "</div>"
    
    html += "<div class=\"maincard\">"
    html += "<h1>Iffy Detections</h1><ul>"

    cur.execute(f"""
    SELECT count(*)  
    FROM detections
    WHERE confidence > ? and confidence < ? and labeled is null and file not like \"recording%\"
    """, [heket_config.CONF_IFFY_MIN, heket_config.CONF_IFFY_MAX])
    max_page = math.ceil( cur.fetchall()[0][0] / limit )

    cur.execute(f"""
    SELECT id, detections.recorded, species, confidence, file, labeled, curated, temp_c, humidity, pressure_mb, rain_rate_mm
    FROM detections left join weather on detections.weather_id = weather.weather_id
    WHERE confidence > ? and confidence < ? and labeled is null and file not like \"recording%\"
    ORDER BY confidence asc
    LIMIT ? offset ?
    """, [heket_config.CONF_IFFY_MIN, heket_config.CONF_IFFY_MAX,limit, (iffy_page - 1) * limit])

    rows = cur.fetchall()
    for r in rows:
        html += f"<li>"
        html += make_detection(id = r[0], recorded = r[1], animal = r[2], confidence = r[3], file = r[4], labeled = r[5], curated = r[6])
        html += "</li>"
        html += "<br>"

    html += "<li style=\"list-style-type: none;\">" + paginate("index", "ip", iffy_page, max_page) + "</li>"
    html += "</ul>"
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


    html += "<div class=\"maincard\">"
    html += "<h1>Bulk Actions</h1>"
    html += f"<ul><h2>Delete Unlabeled</h2>"
    html += "<form method=\"POST\" action=\"detections_delete\" onsubmit=\"return confirm('Are you sure you wish to bulk delete?')\">Start at <input name=\"start\" placeholder=\"2025-01-01T01:23\"> and end at <input name=\"stop\" placeholder=\"2025-01-01T01:23\"> <button type=\"submit\">Delete</button></form>"
    
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
    label = request.form["label"]
    route = None
    if "route" in request.form:
        route = request.form["route"]

    if len(label) == 0:
        return redirect(url_for("index"))

    print(f"Labeling {rec} as {label}")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""select labeled, file from detections where id = ?""", [int(rec)])
    rows = cur.fetchall()
    #this sample was previous labeled... delete the old recording
    #so the labels stay clean
    file = rows[0][1]
    
    if rows[0][0] is not None:
        del_file = os.path.join(heket_config.LABELED_DIR, rows[0][0], file)
        print("Deleted previously labeled file:", del_file)
        heket_common.delete_file( del_file )

    src = Path(os.path.join(heket_config.OUT_DIR, file))
    dst = Path(os.path.join(heket_config.LABELED_DIR, label, file))
    print(f"Copy {src} to {dst}")

    if not dst.exists():
        shutil.copy(src, dst)
        
    # Get existing columns
    cur.execute("""update detections set labeled = ?, curated = ?  where id = ?""", [label, 1, int(rec)])
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
        cmd = 'ffmpeg -i ' + new_filename + ' -ss ' + str(start) + ' -t ' + str(heket_config.SEGMENT_TIME) + ' -ac 1 -ar ' + str(heket_config.SAMPLE_RATE) + ' ' + trimmed_file
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

@app.route("/detections_delete", methods=["POST"])
def detections_delete():
    start = request.form["start"]
    stop = request.form["stop"]

    start_id = 0
    stop_id = 0
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select id, recorded from detections where recorded like ?""", [f"{start}%"])
    rows = cur.fetchall()

    if len(rows) > 0:
        start_id = rows[0][0]

    cur.execute(f"""select id, recorded from detections where recorded like ?""", [f"{stop}%"])
    rows = cur.fetchall()

    if len(rows) > 0:
        stop_id = rows[0][0]

    if stop_id != 0 and start_id != 0:
        cur.execute(f"""select id from detections where id >= ? and id <= ? and curated is null and labeled is null""", [start_id, stop_id])
        rows = cur.fetchall()
        
        recs = []
       
        for r in rows:
            recs.append(r[0])

        detection_delete( recs )

        flash(f"Deleting unlabeled events between {start_id} and {stop_id}")
    else:
        flash("Unable to bulk delete; one or more of the parameters aren't present")

    conn.close()
    return redirect(url_for("index"))

def detection_delete( recs ):
    conn = get_db()
    cur = conn.cursor()

    to_delete = []
    for r in recs:
        cur.execute(f"""select id, file, labeled from detections where id = ?""", [r])
        rows = cur.fetchall()
        if len(rows) > 0:
            to_delete.append( {"id": rows[0][0], "file": rows[0][1], "labeled": rows[0][2]} )

    for d in to_delete:
        #delete the labeled file
        if d["labeled"] is not None:
            heket_common.delete_file(os.path.join(heket_config.LABELED_DIR, d["labeled"], d["file"]))

        #delete the source file
        heket_common.delete_file(os.path.join(heket_config.OUT_DIR, d["file"]))
        
        #delete db record
        cur.execute(f"""delete from detections where id = ?""", [d["id"]])

    conn.commit()
    conn.close()
         
@app.route("/detection_delete", methods=["GET"])
def detection_delete_web():
    rec = int(request.args["id"])
    route = None
    if "route" in request.args:
        route = request.args["route"]
    
    detection_delete([rec])
    
    flash("Detection deleted")
    if route is None:
        return redirect(url_for("index"))
    else:
        return redirect(route)

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
    review_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    html += " The review will start at detection Id " + str(rows[0][0]) + ".</ul>"
    html += review_event_page(review_id)
    return make_page(title = "Review noted", content = html)

def review_event_page(review_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""select detection_id, recorded from reviews where id = ?""", [review_id])
    rows = cur.fetchall()
    detection_id = rows[0][0]
    
    high = detection_id + int((2 * 60) / heket_config.SEGMENT_TIME)
    low = detection_id - int((5 * 60) / heket_config.SEGMENT_TIME)

    html = f"<h1>Review Event</h1><ul>Reported: {rows[0][1]}" + str(rows[0][0]) + f"<br>Detection sequence: {detection_id} ({low} &#x2192; {high})<br><br>"

    cur.execute(f"""SELECT id, detections.recorded, species, confidence, file, labeled, curated, temp_c, humidity, pressure_mb, rain_rate_mm FROM detections left join weather on detections.weather_id = weather.weather_id WHERE id >= ? and id <= ? ORDER BY id DESC """, [low,high])
    
    rows = cur.fetchall()
    for r in rows:
        html += f"<li>"
        route = request.full_path
        #rewrite "frog button" pages to review pages so it doesn't keep creating
        #events
        if "review_process" not in route:
            route = url_for("review_process") + "?id=" + str(review_id)
 
        weather = {"temp_c": r[7], "humidity": r[8], "pressure_mb": r[9], "rain_rate_mm": r[10]}
        html += make_detection(id = r[0], recorded = r[1], animal = r[2], confidence = r[3], file = r[4], labeled = r[5], curated = r[6], weather = weather, route=route)
        html += "</li><br>"
        
    html += f"<br><form method=\"POST\" action=\"review_delete\"><input type=\"hidden\" name=\"id\" value=\"{review_id}\"><button type=\"submit\">Done with review</button></form>"
    html += "</ul>"
    return html

@app.route("/class_save", methods=["POST"])
def class_save():
    class_name = request.form["label_name"]
    latin_name = request.form["latin_name"]
    common_name = request.form["common_name"]
    req = request.form["route"]
    notes = request.form["notes"]
    species_id = None if "species_id" not in request.form  or len(request.form["species_id"]) == 0 else int(request.form["species_id"])

    conn = get_db()
    cur = conn.cursor()
    
    sql_parms = [class_name, latin_name, common_name, notes]
    if species_id is None:
        cur.execute("""INSERT INTO species (label_name, latin_name, common_name, notes) VALUES (?,?,?,?)""",sql_parms)
    else:
        sql_parms.append(species_id)
        cur.execute("""update species set label_name=?, latin_name=?, common_name=?, notes=? where species_id = ?""",sql_parms)

    conn.commit()
    conn.close()
    flash("Class specification save")

    return redirect(req)

@app.route("/class_review", methods=["GET"])
def class_review():
    review_class = request.args["class"]
    
    page = None
    labeled = None
    
    sess_key = "class " + review_class
    if sess_key not in session or not isinstance(session[sess_key], dict):
        session[sess_key] = {}
        
    if "page" in request.args:
        page = int(request.args["page"])
    elif sess_key in session and "page" in session[sess_key]:
        page = int(session[sess_key]["page"])
    else:
        page = 1
    
    if "labeled" in request.args:
        labeled = request.args["labeled"]
    elif sess_key in session and "labeled" in session[sess_key]:
        labeled = session[sess_key]["labeled"]
    else:
        labeled = "B"

    session[sess_key]["page"] = page
    session[sess_key]["labeled"] = labeled

    html = f"<h1>Review Class</h1><ul>"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("select species_id, label_name, latin_name, common_name, notes from species where label_name = ?", [review_class])
    rows = cur.fetchall()
    
    vals = {"id": "", "label_name": "", "latin_name": "", "common_name": "", "notes": ""}
    if len(rows) > 1:
        vals["id"] = rows[0][0]
        vals["label_name"] = rows[0][1]
        vals["latin_name"] = rows[0][2]
        vals["common_name"] = rows[0][3]
        vals["notes"] = rows[0][4]

    html += "<fieldset class=\"collapsible collapsed\" style=\"width: 600px\"><legend>Class Specifics</legend><div class=\"fieldset-content\"><form method=\"POST\" action=\"class_save\">"
    html += f"<input type=\"hidden\" name=\"species_id\" value=\"{vals['id']}\">"
    html += f"<input type=\"hidden\" name=\"route\" value=\"{request.full_path}\">"
    html += f"Label Name:<br><input readonly name=\"label_name\" value=\"{review_class}\"><br><br>"
    html += f"Latin Name:<br><input name=\"latin_name\" value=\"{ vals['latin_name'] if vals['latin_name'] else ''}\"><br><br>"
    html += f"Common Name:<br><input name=\"common_name\" value=\"{ vals['common_name'] if vals['common_name'] else ''}\"><br><br>"
    html += f"Notes:<br><textarea name=\"notes\">{ vals['notes'] if vals['notes'] else ''}</textarea><br><br>"
    html += "<button type=\"submit\">Save</button>"
    html += "</form></div></fieldset>"
    
    sql_pages = f"""SELECT count(*) FROM detections WHERE """
    sql_query = f"""SELECT id, detections.recorded, species, confidence, file, labeled, curated, temp_c, humidity, pressure_mb, rain_rate_mm FROM detections left join weather on detections.weather_id = weather.weather_id  WHERE """
    sql_args = []

    if labeled == "Y":
        sql_query += "labeled = ? "
        sql_args.append(review_class)
        sql_pages += "labeled = ? "
    elif labeled == "N":
        sql_query += "species = ? and labeled is null "
        sql_args.append(review_class)
        sql_pages += "species = ? and labeled is null "
    else:
        sql_query += "(labeled is null and species = ? ) or (labeled = ?)"
        sql_args += [review_class, review_class]
        sql_pages += "(labeled is null and species = ? ) or (labeled = ?)"

    limit = 25
    cur.execute(sql_pages, sql_args)
    max_page = math.ceil( cur.fetchall()[0][0] / limit )

    sql_query += """ORDER BY id DESC LIMIT ? offset ?"""
    sql_args += [limit, (page - 1) * limit]
    cur.execute(sql_query, sql_args)
        
    rows = cur.fetchall()
    
    filter_html = "<fieldset style=\"width: 150px;\"><legend>  Filters  </legend>"
    filter_html += f"<form style=\"display: inline\" method=\"GET\"><input type=\"hidden\" name=\"class\" value=\"{review_class}\">Labeled: <select onchange=\"this.form.submit()\" name=\"labeled\">"
    
    for opt in ["Yes","No","Both"]:
        filter_html += f"<option value=\"{opt[0]}\""
        if labeled == opt[0]:
            filter_html += " selected"
        filter_html += f">{opt}</option>"
    filter_html += "</select></form>" 
    filter_html += "</fieldset><br>"
    filter_html += "<li style=\"list-style-type: none;\">" 
    filter_html += paginate("class_review", "page", page, max_page) + "<br><br>"
    filter_html += "</li>"

    html += filter_html
    for r in rows:
        html += f"<li>"
        weather = {"temp_c": r[7], "humidity": r[8], "pressure_mb": r[9], "rain_rate_mm": r[10]}
        html += make_detection(id = r[0], recorded = r[1], animal = r[2], confidence = r[3], file = r[4], labeled = r[5], curated = r[6], weather = weather, route=request.full_path)
        html += "</li><br>"

    html += "<li style=\"list-style-type: none;\">" + paginate("class_review", "page", page, max_page) + "</li>"
    html += "</ul>"

    return make_page(title = "Review Class", content = html)

@app.route("/review_process", methods=["GET"])
def review_process():
    review_id = int(request.args["id"])
    html = review_event_page(review_id)

    return make_page(title = "Review Event", content = html)

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

@app.route("/curate", methods=["POST"])
def curate():
    rec = int(request.form["rec"])
    route = None
    if "route" in request.form:
        route = request.form["route"]
    curated = None
    if "curated" in request.form and len(request.form["curated"]) > 0:
        curated = int(request.form["curated"])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""update detections set curated = ? where id = ?""", [curated, rec])
    conn.commit()
    conn.close()

    flash("Detection curated")
    if route is None:
        return redirect(url_for("index"))
    else:
        return redirect(route)
    
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

        cur.execute("""SELECT last_insert_rowid()""")
        review_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        html += " The review will start at detection Id " + str(rows[0][0]) + ".</ul>"
        html += review_event_page(review_id)
        return make_page(title = "Review noted", content = html)

    else:
        html += "&#128683; The database had no recordings at that time. Double check your input."
    
    html += "</ul>"
    
    conn.close()
       
    return make_page(title = "Manual review creation", content = html)

@app.route("/spectrogram/<path:id>")
def spectrogram(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select file from detections where id = ?""", [int(id)])
    rows = cur.fetchall()
    file = None
    if len(rows) > 0:
        file = rows[0][0]
        file = os.path.join(heket_config.OUT_DIR, file)
        if not os.path.isfile(file):
            file = None

    conn.close()
    if file is not None:
        buf = heket_classifier.generate_spectrogram(file , "" )
        return send_file(buf, mimetype='image/png')
    else:
        return send_from_directory("web_assets", "unavailable.png")

@app.route("/setup", methods=["GET"])
def setup():
    long_size = 75
    html = ""
    html += "<h1>Setup Heket</h1>"
    html += "<ul>"
    html += "<form action=\"setup_save\" method=\"POST\">"
    html += "<table><tr><th>Parameter</th><th>Value</th></tr>"
    html += f"<tr><td>RTSP URL:</td><td><input name=\"RTSP_URL\" size=\"{long_size}\" value=\"{heket_config.RTSP_URL}\"></td></tr>"
    html += f"<tr><td>Model Sophisication:</td><td><select name=\"MODEL_LEVEL\">"
    for h in heket_config.MODEL_TYPES:
        html += "<option"
        if heket_config.MODEL_LEVEL == h:
            html += " selected"
        html += f">{h}</option>"
    html += "</select>"
    html += "</td></tr>"

    html += f"<tr><td>Confidence Strong:</td><td><input name=\"CONF_STRONG\" size=\"5\" value=\"{heket_config.CONF_STRONG}\"></td></tr>"
    html += f"<tr><td>Iffy Min:</td><td><input name=\"CONF_IFFY_MIN\" size=\"5\" value=\"{heket_config.CONF_IFFY_MIN}\"></td></tr>"
    html += f"<tr><td>Iffy Max:</td><td><input name=\"CONF_IFFY_MAX\" size=\"5\" value=\"{heket_config.CONF_IFFY_MAX}\"></td></tr>"
    html += f"<tr><td>Sample Rate (hz):</td><td><input name=\"SAMPLE_RATE\" size=\"5\" value=\"{str(heket_config.SAMPLE_RATE)}\"></td></tr>"
    html += f"<tr><td>Segment Length (s):</td><td><input name=\"SEGMENT_TIME\" size=\"5\" value=\"{str(heket_config.SEGMENT_TIME)}\"></td></tr>"
    html += f"<tr><td>Weather Provider URL:</td><td><input name=\"WEATHER_PROVIDER\" size=\"{long_size}\" value=\"{str(heket_config.WEATHER_PROVIDER)}\"></td></tr>"
    html += f"<tr><td>Weather Units:</td><td><select name=\"WEATHER_UNITS\">"
    for h in ["imperial","metric"]:
        html += "<option"
        if heket_config.WEATHER_UNITS == h:
            html += " selected"
        html += f">{h}</option>"
    html += "</select>"
    html += "</td></tr>"
    html += f"<tr><td>Notification Provider:</td><td><input name=\"NOTIFICATION_PROVIDER\" size=\"{long_size}\" value=\"{heket_config.NOTIFICATION_PROVIDER}\"></td></tr>"
    html += f"<tr><td>Bout Miniumum Detections:</td><td><input name=\"BOUT_MIN_CLIPS\" size=\"5\" value=\"{heket_config.BOUT_MIN_CLIPS}\"></td></tr>"
    html += f"<tr><td>Bout Maximum Silence (s):</td><td><input name=\"BOUT_MAX_SILENT\" size=\"5\" value=\"{heket_config.BOUT_MAX_SILENT}\"></td></tr>"
    html += f"<tr><td>Latitude:</td><td><input name=\"LAT\" size=\"15\" value=\"{heket_config.LAT}\"></td></tr>"
    html += f"<tr><td>Longitude:</td><td><input name=\"LON\" size=\"15\" value=\"{heket_config.LON}\"></td></tr>"
    html += "</table><br>"
    html += "<button type=\"submit\">Save</button>"
    html += "</form><br>"
    
    if False:
        html += "<h2>Link to TurtlePond.us</h2>TurtlePond.us can help you easily share recordings with sites such as iNaturalist. No complicated registration required.<br><br>"
        ok = False
        if heket_config.TURTLEPOND_KEY == None or not heket_common.test_key():
            html += "The link has not been established or is broken."
        else:
            html += "The link is working correctly."
            ok = True
            
        html += "  <form style=\"display: inline\" method=\"POST\" action=\"turtlepond_link\" onsubmit=\"return confirm('Do you want to reconnect?')\"><button type=\"submit\">Reconnect</button></form>"

        if ok:
            html += "<br><br><form method=\"POST\" action=\"turtlepond_manage\"><button type=\"submit\">Manage Integrations</button></form>"
            
    html += "</ul>"

    return make_page(title = "Setup", content = html)

@app.route("/turtlepond_link", methods=["POST"])
def turtlepond_link():
    key = heket_common.key_generate()

    try:
        response = requests.post(heket_config.TURTLEPOND + "device_register", json={"device_key": key})

        if response.status_code == 200:
            heket_config.save_config_value("HEKET_TURTLEPOND_KEY",key)
            heket_config.TURTLEPOND_KEY = key
            res = response.json()
            return make_page(title="Complete Linking", content=f"<h1>Complete Linking</h1><ul>To complete the link, enter this code: {res['challenge']} on the <a href=\"{res['challenge_url']}\">TurtlePond</a> website within a few minutes.</ul>")
        else:
            return make_page(title="Link Failed", content="<h1>Linking Failed</h1>Please try again later.")
    except Exception as e:
        return make_page(title="Link Failed", content="<h1>Linking Failed</h1>Please try again later.")
        
@app.route("/turtlepond_manage", methods=["POST"])
def turtlepond_manage():
    try:
        response = requests.get(heket_config.TURTLEPOND + "session_create", headers={'X-Heket-ID': heket_config.TURTLEPOND_KEY})
        if response.status_code == 200:
            res = response.json()
            return redirect(res["url"])
        else:
            return make_page(title="Management Failed", content="<h1>Management Failed</h1>Please try again later.")
    except Exception as e:
        return make_page(title="Management Failed", content="<h1>Management Failed</h1>Please try again later.")

@app.route("/setup_save", methods=["POST"])
def setup_save():
    rtsp_url = request.form["RTSP_URL"]
    conf_strong = request.form["CONF_STRONG"]
    iffy_min = request.form["CONF_IFFY_MIN"]
    iffy_max = request.form["CONF_IFFY_MAX"]
    model_level = request.form["MODEL_LEVEL"]
    sample_rate = request.form["SAMPLE_RATE"]
    segment_len = request.form["SEGMENT_TIME"]
    weather_prov = request.form["WEATHER_PROVIDER"]
    weather_units = request.form["WEATHER_UNITS"]
    notif_prov = request.form["NOTIFICATION_PROVIDER"]
    bout_clips = request.form["BOUT_MIN_CLIPS"]
    bout_silence = request.form["BOUT_MAX_SILENT"]
    lat = request.form["LAT"]
    lon = request.form["LON"]
    
    heket_config.save_config_value("HEKET_RTSP_URL",rtsp_url)
    heket_config.save_config_value("HEKET_CONF_STRONG",conf_strong)
    heket_config.save_config_value("HEKET_CONF_IFFY_MIN",iffy_min)
    heket_config.save_config_value("HEKET_CONF_IFFY_MAX",iffy_max)
    heket_config.save_config_value("HEKET_MODEL_LEVEL",model_level)
    heket_config.save_config_value("HEKET_SAMPLE_RATE",sample_rate)
    heket_config.save_config_value("HEKET_SEGMENT_TIME",segment_len)
    heket_config.save_config_value("HEKET_WEATHER_PROVIDER",weather_prov)
    heket_config.save_config_value("HEKET_WEATHER_UNITS",weather_units)
    heket_config.save_config_value("HEKET_NOTIFICATION_PROVIDER", notif_prov)
    heket_config.save_config_value("HEKET_BOUT_MIN_CLIPS", bout_clips)
    heket_config.save_config_value("HEKET_BOUT_MAX_SILENT", bout_silence)
    heket_config.save_config_value("HEKET_LAT", lat)
    heket_config.save_config_value("HEKET_LON", lon)
    
    signal_pipeline()
    heket_config.reload()

    flash("Configuration saved")
    return redirect(url_for("index"))
    
@app.route("/model_train", methods=["POST"])
def model_train():
    global TRAINING
    if TRAINING is None:
        TRAINING = subprocess.Popen(["python", "heket_train.py"])
        flash("Model training initiated")
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

@app.route("/bout_create", methods=["POST"])
def bout_create():
    bout_start = request.form["bout_start"]
    bout_end = request.form["bout_end"]
    species = request.form["label"]
    
    bout_start_id = None
    bout_end_id = None
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select min(id) from detections where recorded like ?""", [f"{bout_start}%"])
    rows = cur.fetchall()
    if len(rows) > 0:
        bout_start_id = rows[0][0]
    else:
        flash("Bout start time not found")
        
    cur.execute(f"""select max(id) from detections where recorded like ?""", [f"{bout_end}%"])
    rows = cur.fetchall()
    if len(rows) > 0:
        bout_end_id = rows[0][0]
    else:
        flash("Bout end time not found")

    if bout_start_id is not None and bout_end_id is not None and bout_start_id > bout_end_id:
        temp = bout_start_id
        bout_start_id = bout_end_id
        bout_end_id = temp
        
    # so we have the start and end now.. we need the information for the bout
    cur.execute(f"""select min(recorded), max(recorded), min(confidence), max(confidence), avg(confidence), count(*) 
        from detections where id >= ? and id <= ? and bout_id is null and ((species = ? and labeled is null) or (labeled = ?))""", [bout_start_id, bout_end_id, species, species])
    rows = cur.fetchall()
    if len(rows) > 0:
        cur.execute(f"""insert into bouts (species, start_detection_id, end_detection_id, start_ts, end_ts, conf_min, conf_max, conf_avg, clips) values (?,?,?,?,?,?,?,?,?)""",[species, bout_start_id, bout_end_id] + list(rows[0]))
        bout_id = cur.lastrowid
        cur.execute(f"""update detections set bout_id = ? where  id >= ? and id <= ? and bout_id is null and ((species = ? and labeled is null) or (labeled = ?))""",[bout_id, bout_start_id, bout_end_id, species, species])
        conn.commit()
        flash("Bout created")
    else:
        flash("No clips found for bout")

    return redirect(url_for("index"))

@app.route("/bout_delete", methods=["GET"])
def bout_delete():
    bout_id = int(request.args["id"])

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""update detections set bout_id = null where bout_id = ?""", [bout_id])
    cur.execute(f"""delete from bouts where bout_id = ?""", [bout_id])
    conn.commit()
    flash("Bout deleted")

    return redirect(url_for("index"))

@app.route("/bout_note", methods=["POST"])
def bout_note():
    bout_id = int(request.form["bout_id"])
    note = request.form["note"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""update bouts set notes =? where bout_id = ?""", [note, bout_id])
    conn.commit()

    flash("Bout note saved")

    return redirect(url_for("bout_review",bout_id=bout_id))

@app.route("/bout_review", methods=["GET"])
def bout_review():
    bout_id = int(request.args["bout_id"])

    # this is ugly and largely ripped out of the class review
    # it should probably not be
    
    page = None
    labeled = None
    
    sess_key = "bout " + str(bout_id)
    if sess_key not in session or not isinstance(session[sess_key], dict):
        session[sess_key] = {}
        
    if "page" in request.args:
        page = int(request.args["page"])
    elif sess_key in session and "page" in session[sess_key]:
        page = int(session[sess_key]["page"])
    else:
        page = 1
    
    if "labeled" in request.args:
        labeled = request.args["labeled"]
    elif sess_key in session and "labeled" in session[sess_key]:
        labeled = session[sess_key]["labeled"]
    else:
        labeled = "B"

    session[sess_key]["page"] = page
    session[sess_key]["labeled"] = labeled

    html = f"<h1>Review Bout</h1><ul>"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""select notes from bouts where bout_id = ?""",[bout_id])
    rows = cur.fetchall()
    html += f"<form method=\"POST\" action=\"bout_note\"><input type=\"hidden\" name=\"bout_id\" value=\"{bout_id}\">"
    html += "Notes:<br><textarea name=\"note\" rows=\"5\" cols=\"50\">"
    if rows[0][0] is not None:
        html += rows[0][0]
    html += "</textarea> <button type=\"submit\">Save</button>"
    html += "</form>"

    sql_pages = f"""SELECT count(*) FROM detections WHERE """
    sql_query = f"""SELECT id, detections.recorded, species, confidence, file, labeled, curated, temp_c, humidity, pressure_mb, rain_rate_mm FROM detections left join weather on detections.weather_id = weather.weather_id  WHERE """
    sql_args = []

    if labeled == "Y":
        sql_query += "labeled is not null "
        sql_pages += "labeled is not null "
    elif labeled == "N":
        sql_query += "labeled is null "
        sql_pages += "labeled is null "
    else:
        sql_query += "species is not null "
        sql_pages += "species is not null "

    sql_query += "and bout_id = ?"
    sql_pages += "and bout_id = ?"
    sql_args += [bout_id]

    limit = 25
    cur.execute(sql_pages, sql_args)
    max_page = math.ceil( cur.fetchall()[0][0] / limit )

    sql_query += """ORDER BY id DESC LIMIT ? offset ?"""
    sql_args += [limit, (page - 1) * limit]
    cur.execute(sql_query, sql_args)
        
    rows = cur.fetchall()
    
    filter_html = "<fieldset style=\"width: 150px;\"><legend>  Filters  </legend>"
    filter_html += f"<form style=\"display: inline\" method=\"GET\"><input type=\"hidden\" name=\"bout_id\" value=\"{bout_id}\">Labeled: <select onchange=\"this.form.submit()\" name=\"labeled\">"
    
    for opt in ["Yes","No","Both"]:
        filter_html += f"<option value=\"{opt[0]}\""
        if labeled == opt[0]:
            filter_html += " selected"
        filter_html += f">{opt}</option>"
    filter_html += "</select></form>" 
    filter_html += "</fieldset><br>"
    filter_html += "<li style=\"list-style-type: none;\">" 
    filter_html += paginate("bout_review", "page", page, max_page) + "<br><br>"
    filter_html += "</li>"

    html += filter_html
    for r in rows:
        html += f"<li>"
        weather = {"temp_c": r[7], "humidity": r[8], "pressure_mb": r[9], "rain_rate_mm": r[10]}
        html += make_detection(id = r[0], recorded = r[1], animal = r[2], confidence = r[3], file = r[4], labeled = r[5], curated = r[6], weather = weather, route=request.full_path)
        html += "</li><br>"

    html += "<li style=\"list-style-type: none;\">" + paginate("bout_review", "page", page, max_page) + "</li>"
    html += "</ul>"

    return make_page(title = "Review Bout", content = html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
	
