import shutil
import os
import heket_config
import sqlite3
import random
import requests
import subprocess
from pathlib import Path
import sys

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

    if False:
        CONN.cursor().execute("""
        CREATE TABLE IF NOT EXISTS detection_slices (
            slice_id INTEGER PRIMARY KEY AUTOINCREMENT,
            detection_id integer,
            prediction TEXT,
            confidence REAL,
            labeled TEXT,
            curated integer,
            offset real,
            duration real
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
        start_ts int,
        end_ts int,
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

def version_number(version):
    major, minor = str(version).split(".")
    return int(major) * 100 + int(minor)


def migrate_versions():
    print("Heket migration level was at version", heket_config.LAST_MIGRATED_VERSION)
    print("Heket software is at version", heket_config.VERSION)

    if heket_config.VERSION != heket_config.LAST_MIGRATED_VERSION:
        print("Searching for migration scripts...")
        start_version = version_number(heket_config.LAST_MIGRATED_VERSION)
        end_version = version_number(heket_config.VERSION)

        for i in range(start_version, end_version):
            start = f"{i / 100:.2f}"
            stop = f"{(i + 1) / 100:.2f}"

            file = f"migration/{start}_to_{stop}.py"

            if Path(file).exists():
                print("Execute", file)
                subprocess.run([sys.executable,file], check=True)
                heket_config.save_config_value("HEKET_LAST_VERSION",stop)
            #subprocess.Popen(["python","migration/{file}.py"])
    else:
        print("No migration necessary.")

migrate_versions()