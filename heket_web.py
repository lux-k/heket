from flask import Flask, send_from_directory
import sqlite3
import heket_config
import os

app = Flask(__name__)

def get_db():
    return sqlite3.connect(heket_config.DB_FILE)

@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT recorded, species, confidence, file
    FROM detections
    WHERE confidence > 0.2
    ORDER BY recorded DESC
    LIMIT 10
    """)

    rows = cur.fetchall()

    html = "<h1>Recent Frog Detections</h1><ul>"

    for r in rows:
        html += f"<li>{r[0]} — {r[1]} ({r[2]:.2f})<audio controls src=\"recordings/{r[3]}\"></audio></li>"

    html += "</ul>"


    cur.execute("""
    SELECT species, count(*)
    FROM detections
    WHERE confidence > 0.2
	GROUP BY species
    ORDER BY count(*) DESC
    """)

    rows = cur.fetchall()

    html += "<h1>Total Detections by Species</h1><ul>"

    for r in rows:
        html += f"<li>{r[0]} — {r[1]}</li>"

    html += "</ul>"

    conn.close()

    return html

@app.route("/recordings/<path:filename>")
def files(filename):
    return send_from_directory(heket_config.OUT_DIR, filename)
	
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
	
