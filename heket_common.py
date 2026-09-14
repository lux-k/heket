import shutil
import os
import heket_config
import sqlite3
import random
import requests

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
        recorded_ts int,
        processed_ts int,
        species TEXT,
        confidence REAL,
        file TEXT,
        labeled TEXT,
        curated integer,
        weather_id integer,
        bout_id integer
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

    CONN.cursor().execute("""
    CREATE TABLE IF NOT EXISTS bouts (
        bout_id INTEGER PRIMARY KEY AUTOINCREMENT,
        species TEXT,
        start_detection_id integer,
        end_detection_id integer,
        start_ts text,
        end_ts text,
        conf_min real,
        conf_max real,
        conf_avg real,
        clips integer,
        notes text
    )
    """)

    CONN.cursor().execute("""
    CREATE TABLE IF NOT EXISTS species (
        species_id INTEGER PRIMARY KEY AUTOINCREMENT,
        label_name TEXT,
        latin_name TEXT,
        common_name TEXT,
        notes text
    )
    """)

    CONN.cursor().execute("""
    CREATE TABLE IF NOT EXISTS detection_shares (
        share_id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT,
        provider_id text,
        detection_id int,
        share_ts int
    )
    """)

    CONN.commit()
    CONN.close()

def key_generate():
    key = ""
    
    src = ""
    for i in range(48, 58):
        src += chr(i)

    for i in range(65, 127):
        src += chr(i)
    
    src_len = len(src)
    for i in range(65):
        spot = random.randint(0,src_len - 1)
        key += src[spot:spot + 1]
        
    return key

def test_key():
    try:
        print(heket_config.TURTLEPOND + "device/ping")
        response = requests.get(heket_config.TURTLEPOND + "device/ping", headers={'X-Heket-ID': heket_config.TURTLEPOND_KEY})
        
        if response.status_code == 200:
            return True, response.json()
        else:
            return False
    except Exception as e:
        return False