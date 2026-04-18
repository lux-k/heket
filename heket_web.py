from flask import Flask, send_from_directory, request, redirect, url_for
import sqlite3
import heket_config
import os
import shutil
from pathlib import Path
import subprocess
import signal
from datetime import datetime


LABEL_CANDS = []
CUSTOM_MODELS = []

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

def get_db():
    return sqlite3.connect(heket_config.DB_FILE)

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

def make_page(title = "Home", content = ""):
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
</script>
<link rel="stylesheet" href="web_assets/style.css">
</head><body>
"""    
    html += "<div class=\"floater\"><form method=\"GET\" action=\"review_add\"><button style=\"height: 60px; background: var(--heket-light-gold); line-height: 1.5;\">&#128056;<br>Frog Calling</button></form></div>"
    url = url_for("index")
    html += f"<center><a href=\"{ url }\"><img src=\"/web_assets/heket_logo_small.png\"></a></center><br>"
    html += content
    html += "<br><center><div style=\"margin-bottom: 20px\">"
    html += f"Heket v{heket_config.VERSION} by <a href=\"mailto:kevin@turtlepond.us\">Kevin Lux</a>; Github <a href=\"https://github.com/lux-k/heket\"><img height=\"15\" width=\"15\" src=\"web_assets/github.svg\"></a>; <a href=\"https://turtlepond.us\">TurtlePond.us</a><br>"
    html += "</div></center></body></html>"
    return html

def make_label_form(rec = None, file = None, route = None):
    html = "<form method=\"POST\" action=\"/label\">"
    html += f"<audio controls style=\"height:10px;\" src=\"recordings/{file}\"></audio>"
    html += f"<input type=\"hidden\" name=\"rec\" value=\"{rec}\">"
    html += f"<input type=\"hidden\" name=\"file\" value=\"{file}\">"
    
    if route is not None:
        html += f"<input type=\"hidden\" name=\"route\" value=\"{route}\">"
    
    html += f"<select name=\"label\">"
    html += f"<option></option>"
    for label in LABEL_CANDS:
        html += f"<option>{label}</option>"
    html += "</select> "
    html += "<button type=\"submit\">Label</button>"
    html += "</form>"
    return html

@app.route("/")
def index():
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
    WHERE confidence > {heket_config.CONF_STRONG} and animal not like \"nonfrog_%\"
    ORDER BY recorded DESC
    LIMIT {limit}
    """)

    rows = cur.fetchall()

    html = "<table cellspacing=\"5\" width=\"100%\"><tr><td width=\"33%\" valign=\"top\">"
    html += "<h1>Strong Frog Detections</h1><ul>"

    for r in rows:
        html += f"<li>{r[1]} — {r[2]} ({r[3]:.2f})"
        html += "<div style=\"display:flex; align-items:center; gap:10px; line-height:1;\">"
        html += make_label_form( rec = r[0], file = r[4] )
        html += "</div>"
        html += "</li><br>"

    html += "</ul>"
    html += "</td><td width=\"33%\" valign=\"top\"><h1>Iffy Detections</h1>"

    cur.execute(f"""
    SELECT id, recorded, species, confidence, file
    FROM detections
    WHERE confidence > {heket_config.CONF_IFFY_MIN} and confidence < {heket_config.CONF_IFFY_MAX} and labeled is null and file not like \"recording%\"
    ORDER BY confidence asc
    LIMIT {limit}
    """)

    rows = cur.fetchall()
    for r in rows:
        html += f"<li>{r[1]} — {r[2]} ({r[3]:.2f})"
        html += make_label_form( rec = r[0], file = r[4] )
        html += "</li><br>"

    html += "</ul>"
    html += "</td><td width=\"33%\" valign=\"top\"><h1>Detections by Species</h1><ul>"
    
    cur.execute(f"""
    SELECT 
            CASE 
            when labeled is null THEN species
            when labeled is not null then labeled
        END as animal,
    count(*)
    FROM detections
    WHERE animal not like \"nonfrog_%\"
    GROUP BY animal
    ORDER BY count(*) DESC
    """)

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
    WHERE animal like \"nonfrog_%\"
    GROUP BY animal
    ORDER BY count(*) DESC
    """)

    rows = cur.fetchall()

    if len(rows) == 0:
        html += f"<li><i>none</i></li>"
    else:
        for r in rows:
            html += f"<li>{r[0]} — {r[1]}</li>"    
    html += "</td></tr><tr>"
    

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
    
    html += "</td><td valign=\"top\"><h1>Model</h1>"
    html += f"<ul><h2>Current</h2><ul><span class=\"accent\">{Path(heket_config.MODEL_FILE).name}</span></ul></ul>"
    html += "<ul><h2>Available <form style=\"display: inline;\" method=\"POST\" action=\"model_reload\"><button type=\"submit\">&#10227;</button></form></h2><ul>"
    if len(CUSTOM_MODELS) == 0:
        html += "<i>none</i>"
    else:
        for m in CUSTOM_MODELS:
            html += f"<a href=\"model_switch?model={m}\">{m}</a><br>"
            
    html += "</ul><h2>Train</h2><ul>"
    html += "<form method=\"POST\" action=\"/model_train\"><button type=\"submit\">Train</button></form></ul>"
    html += "</ul></td><td valign=\"top\">"
    html += "<h1>Labels</h1><ul><h2>Add</h2><ul><form method=\"POST\" action=\"/label_add\">New label: <input name=\"label\"> <button type=\"submit\">Add Label</button></form></ul></ul>"
    html += "</tr></table>"
    conn.close()

    return make_page(title = "Dashboard", content = html)

@app.route("/web_assets/<path:filename>")
def assets(filename):
    return send_from_directory("web_assets", filename)

@app.route("/recordings/<path:filename>")
def files(filename):
    return send_from_directory(heket_config.OUT_DIR, filename)

@app.route("/label", methods=["POST"])
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
    cur.execute("""update detections set labeled = ? where id = ?""", (label, int(rec)))
    conn.commit()
    conn.close()

    
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
    return redirect(url_for("index"))

@app.route("/model_reload", methods=["POST"])
def model_reload():
    update_models()
    return redirect(url_for("index"))

@app.route("/model_switch", methods=["GET"])
def model_switch():
    model = request.args["model"]
    
    if len(model) == 0:
        return redirect(url_for("index"))
    
    model = os.path.join(heket_config.CUSTOM_MODEL_DIR, model)
    with open(os.path.join(heket_config.DATA_DIR, "current_model.txt"), "w") as f:
        f.write( model )
    
    signal_pipeline()
    heket_config.reload()
   
    return redirect(url_for("index"))

@app.route("/review_add", methods=["GET"])
def review_add():

    html = "<h1>Review Noted</h1><ul>&#9989; Thanks for reporting the frog call."

    conn = get_db()
    cur = conn.cursor()
    cur.execute("select max(id) from detections")
    rows = cur.fetchall()
    detection_id = rows[0][0]
    
    cur.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id integer,
    recorded TEXT
)
""")
    cur.execute("""insert into reviews (detection_id, recorded) values (?,?)""", (int(detection_id), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    html += " The review will start at detection Id " + str(rows[0][0]) + ".</ul>"
    return make_page(title = "Review noted", content = html)
    
@app.route("/review_process", methods=["GET"])
def review_process():
    review_id = request.args["id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""select detection_id, recorded from reviews where id = ?""", (review_id))
    rows = cur.fetchall()
    detection_id = rows[0][0]
    
    high = detection_id + int((2 * 60) / heket_config.SEGMENT_TIME)
    low = detection_id - int((5 * 60) / heket_config.SEGMENT_TIME)

    html = f"<h1>Review</h1><ul>Reported: {rows[0][1]}" + str(rows[0][0]) + f"<br>Detection sequence: {detection_id} ({low} &#x2192; {high})<br><br>"

    cur.execute(f"""SELECT id, recorded, species, confidence, file FROM detections WHERE id >= ? and id <= ? ORDER BY id DESC """, (low,high))
    
    rows = cur.fetchall()
    for r in rows:
        html += f"<li>{r[1]} — {r[2]} ({r[3]:.2f})"
        html += make_label_form( rec = r[0], file = r[4], route = request.full_path )
        html += "</li><br>"
    html += f"<br><form method=\"POST\" action=\"review_delete\"><input type=\"hidden\" name=\"id\" value=\"{review_id}\"><button type=\"submit\">Done with review</button></form>"
    html += "</ul>"


    return make_page(title = "Review noted", content = html)

@app.route("/review_delete", methods=["POST"])
def review_delete():
    review_id = request.form["id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""delete from reviews where id = ?""", (review_id))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/review_manual", methods=["POST"])
def review_manual():
    time = request.form["time"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""select id, recorded from detections where recorded like \"{time}%\"""")
    rows = cur.fetchall()
    html = "<h1>Event Creation</h1><ul>"
    if len(rows) > 0:
        detection_id = rows[0][0]
     
        cur.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        detection_id integer,
        recorded TEXT
    )
    """)
        cur.execute("""insert into reviews (detection_id, recorded) values (?,?)""", (int(detection_id), rows[0][1]))
        conn.commit()
        html += "&#9989; The event was found and created."
    else:
        html += "&#128683; The database had no recordings at that time. Double check your input."
    
    html += "</ul>"
    
    conn.close()
        
    return make_page(title = "Manual review creation", content = html)
    
#    return redirect(url_for("index"))
    
@app.route("/model_train", methods=["POST"])
def model_train():
    subprocess.Popen(["python", "heket_train.py"])
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
	
