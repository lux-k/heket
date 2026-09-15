import tarfile
import sys
import json
import os
from pathlib import Path

parent_dir = str(Path(__file__).resolve().parent.parent)

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import heket_common
import heket_config
import turtlepond.storage
import turtlepond.dates

if len(sys.argv) != 2:
    print("Provide the label to create")
    sys.exit()

label = sys.argv[1]

def init_storage():
    STORAGE_CFG = json.loads(os.getenv("HEKET_STORAGE_CFG", '{"fs": {"base": "' + heket_config.REC_DIR + '"}}'))

    backend = next(iter(STORAGE_CFG))
    return turtlepond.storage.create(type=backend, configuration=STORAGE_CFG[backend])

def get_contrib_path(file):
    return "contrib/" + file[-3:] + "/" + file

STORAGE = init_storage()
DB = heket_common.get_db()

SR = 16000
DURATION = 15

cur = DB.cursor()
cur.execute(f"""select filename,  filesize from contrib_clips where turtlepond_label = ? and audio_sr = ? and audio_duration > ? - .1 and audio_duration < ? + .1 and filesize is not null order by random() limit 200""", [label, SR, DURATION, DURATION])
rows = cur.fetchall()
print(rows)

temp_tar = f"/tmp/tmp.tar"

with tarfile.open(temp_tar, "w") as tar:
    for r in rows:
        with STORAGE.open(get_contrib_path(r[0])) as src:
            info = tarfile.TarInfo(name=f"{r[0]}.wav")
            info.size = r[1]

            tar.addfile(info, fileobj=src)

filename = f"{label}_{str(SR)}Hz_{str(DURATION)}s.tar"

STORAGE.put_file(f"packs/{label}/{filename}", temp_tar)

cur.execute("delete from clip_packs where label = ? and audio_sr = ? and duration = ?",[label, SR, DURATION])
cur.execute("insert into clip_packs (label, audio_sr, duration, file, update_ts) values (?,?,?,?,?)",[label, SR, DURATION, filename, turtlepond.dates.get_epoch()])
DB.commit()