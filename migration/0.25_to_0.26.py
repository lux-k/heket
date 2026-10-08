import sys
from pathlib import Path
import os

parent_dir = str(Path(__file__).resolve().parent.parent)

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import heket_config
import heket_common
import turtlepond.dates
import heket_audio_source

#move from single source to multi-source
CONN = heket_common.get_db()
curr = CONN.cursor()

curr.execute("""ALTER TABLE detections add source_id int""")
if len(heket_config.RTSP_URL) > 0:
    print("Migrating config to audio source...")
    vals = {}
    vals["type"] = "rtsp"
    vals["name"] = "Heket RTSP source"
    vals["enabled"] = "on"
    vals["latitude"] = heket_config.LAT
    vals["longitude"] = heket_config.LON
    vals["endpoint_url"] = heket_config.RTSP_URL
    vals["sr"] = heket_config.SAMPLE_RATE
    vals["segment_length"] = heket_config.SEGMENT_TIME
    curr.execute(f"""insert into sources (type, name, lat, lon, config,enabled,updated_ts) values (?,?,?,?,?,?,?)""",
                [vals["type"], vals["name"], vals["latitude"], vals["longitude"], heket_audio_source.toJson(values=vals), 1, turtlepond.dates.get_epoch()])
    curr.execute("update detections set source_id = 1")

    CONN.commit()

heket_config.delete_config_value('HEKET_RTSP_URL')
heket_config.delete_config_value('HEKET_LAT')
heket_config.delete_config_value('HEKET_LON')

CONN.commit()
CONN.close()