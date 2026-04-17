from flask import Flask, send_from_directory, request, redirect, url_for
import sqlite3
import heket_config
import os
import shutil
from pathlib import Path
import subprocess
import signal

LABEL_CANDS = []
CUSTOM_MODELS = []

def update_labels():
    global LABEL_CANDS
    LABEL_CANDS = sorted([p.name for p in Path(heket_config.LABELED_DIR).iterdir() if p.is_dir()])

def update_models():
    global CUSTOM_MODELS
    
    cm_dir = Path(heket_config.CUSTOM_MODEL_DIR)
    if cm_dir.is_dir():
        CUSTOM_MODELS = sorted([p.name for p in cm_dir.iterdir() if str(p).endswith(".pkl")])
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
        conn.commit()
    else:
        print(f"Column {column} already exists")

def get_db():
    return sqlite3.connect(heket_config.DB_FILE)

CONN = get_db()
ensure_column(CONN, "detections", "labeled", "TEXT")
CONN.close()

app = Flask(__name__)


def make_label_form(rec = None, file = None):
    html = "<form method=\"POST\" action=\"/label\">"
    html += f"<audio controls style=\"height:10px;\" src=\"recordings/{file}\"></audio>"
    html += f"<input type=\"hidden\" name=\"rec\" value=\"{rec}\">"
    html += f"<input type=\"hidden\" name=\"file\" value=\"{file}\">"
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
    SELECT id, recorded, species, confidence, file
    FROM detections
    WHERE confidence > {heket_config.CONF_STRONG}
    ORDER BY recorded DESC
    LIMIT {limit}
    """)

    rows = cur.fetchall()

    html = f"<html><head><title>Heket v{heket_config.VERSION}</title>"
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
    html += "<center><img src=\"/web_assets/heket_logo_small.png\"></center><br>"
    html += "<table cellspacing=\"5\" width=\"100%\"><tr><td width=\"33%\" valign=\"top\">"
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
    ORDER BY confidence DESC
    LIMIT {limit}
    """)

    rows = cur.fetchall()
    for r in rows:
        html += f"<li>{r[1]} — {r[2]} ({r[3]:.2f})"
        html += make_label_form( rec = r[0], file = r[4] )
        html += "</li><br>"

    html += "</ul>"
    html += "</td><td width=\"33%\" valign=\"top\"><h1>Total Detections by Species</h1><ul>"
    
    cur.execute("""
    SELECT species, count(*)
    FROM detections
    WHERE confidence > 0.2
    GROUP BY species
    ORDER BY count(*) DESC
    """)

    rows = cur.fetchall()

    for r in rows:
        html += f"<li>{r[0]} — {r[1]}</li>"

    html += "</ul>"
    html += "</td></tr><tr><td valign=\"top\"><h1>Model</h1>"
    html += f"<ul><h2>Current Model</h2><ul><span class=\"accent\">{Path(heket_config.MODEL_FILE).name}</span></ul></ul>"
    html += "<ul><h2>Custom Models <form style=\"display: inline;\" method=\"POST\" action=\"model_reload\"><button type=\"submit\">&#10227;</button></h2><ul>"
    if len(CUSTOM_MODELS) == 0:
        html += "<i>none</i>"
    else:
        for m in CUSTOM_MODELS:
            html += f"<a href=\"model_switch?model={m}\">{m}</a><br>"
            
    html += "</ul><h2>Train Model</h2><ul>"
    html += "<form method=\"POST\" action=\"/model_train\"><button type=\"submit\">Train</button></form></ul>"
    html += "</ul></td><td valign=\"top\">"
    html += "<h1>Labels</h1><ul><h2>Add Label</h2><ul><form method=\"POST\" action=\"/label_add\">New label: <input name=\"label\"> <button type=\"submit\">Add Label</button></form></ul></ul>"
    html += "</tr></table><br><center><div style=\"margin-bottom: 20px\">"
    html += f"Heket v{heket_config.VERSION} by <a href=\"mailto:kevin@turtlepond.us\">Kevin Lux</a>; Github <a href=\"https://github.com/lux-k/heket\"><img height=\"15\" width=\"15\" src=\"web_assets/github.svg\"></a>; <a href=\"https://turtlepond.us\">TurtlePond.us</a><br>"
    html += "</div></center></body></html>"
    conn.close()

    return html

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
    cur.execute(f"update detections set labeled = \"{label}\" where id = {rec}")
    conn.commit()
    conn.close()

    return redirect(url_for("index"))
	
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
	
