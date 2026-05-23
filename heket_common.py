import shutil
import os
import heket_config
import sqlite3

def delete_file(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass  # already gone, no big deal
    except Exception as e:
        print(f"Error deleting {path}: {e}")

def move_file(src, dst):
    try:
        shutil.move(src, dst)
    except Exception as e:
        print(f"Error moving {src} → {dst}: {e}")

def get_db():
    return sqlite3.connect(heket_config.DB_FILE)

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
    CONN.cursor().execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        detection_id integer,
        recorded TEXT
    )
    """)
    
    CONN.cursor().execute("""
    CREATE TABLE IF NOT EXISTS detections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded TEXT,
        processed TEXT,
        species TEXT,
        confidence REAL,
        file TEXT,
        labeled TEXT,
        curated integer,
        weather_id integer
    )
    """)

    CONN.cursor().execute("""
    CREATE TABLE IF NOT EXISTS weather (
        weather_id INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded TEXT,
        temp_c REAL,
        humidity real,
        pressure_mb REAL,
        rain_rate_mm integer
    )
    """)

    ensure_column(CONN, "detections", "labeled", "TEXT")
    ensure_column(CONN, "detections", "curated", "INT")
    ensure_column(CONN, "detections", "weather_id", "INT")

    CONN.commit()
    CONN.close()
