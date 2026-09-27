import sys
from pathlib import Path
import os

parent_dir = str(Path(__file__).resolve().parent.parent)

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import heket_config
import heket_common

#accomodate schema changes...

#all target/non-targets to be defined via class metadata
CONN = heket_common.get_db()
curr = CONN.cursor()
if True:
    #detections provenance
    curr.execute("""ALTER TABLE detections add duration real""")
    curr.execute("""ALTER TABLE detections add sample_rate integer""")
    curr.execute("""alter table detections add model_id int""")
    curr.execute("""update detections set duration = ?""", [heket_config.SEGMENT_TIME])
    curr.execute("""update detections set sample_rate = ?""", [heket_config.SAMPLE_RATE])
    curr.execute("""alter table bouts rename column species to label""")
    
    curr.execute("""
    CREATE TABLE IF NOT EXISTS detection_slices (
        slice_id INTEGER PRIMARY KEY AUTOINCREMENT,
        detection_id integer,
        prediction TEXT,
        confidence REAL,
        labeled TEXT,
        curated integer,
        offset real,
        duration real,
        bout_id int
        )
    """)

    curr.execute("""select id, species, confidence, labeled, bout_id, curated from detections""")

    rows = curr.fetchall()

    for r in rows:
        curr.execute("""insert into detection_slices (detection_id, prediction, confidence, labeled, offset, duration, bout_id, curated) 
                    values (?,?,?,?,?,?,?,?)""", [r[0], r[1], r[2], r[3], 0, heket_config.SEGMENT_TIME,r[4],r[5]])

    print("Reorganizing labeled clips")
    for l in heket_common.labels_get():
        mylen = str(heket_config.SLICE_TIME)
        mylen = mylen.replace(".","_")

        contrib = os.path.join(Path(heket_config.CONTRIB_DIR), l)

        if Path(contrib).exists():
            #os.makedirs(dst_path, exist_ok=True)
            new_path = os.path.join(contrib, mylen + "s")
            print("Create", new_path)
            os.makedirs(new_path, exist_ok = True)

            files = [x for x in Path(contrib).iterdir() if x.is_file()]
            for f in files:
                new_file = os.path.join(new_path, Path(f).stem + "_0_0" + Path(f).suffix)
                print("Move ", f, "to", new_file)
                heket_common.move_file(f, new_file)
        
        labeled = os.path.join(Path(heket_config.LABELED_DIR), l)
        if Path(labeled).exists():
            print(labeled, "exists")
            #os.makedirs(dst_path, exist_ok=True)
            new_path = os.path.join(labeled, mylen + "s")
            print("Create", new_path)
            os.makedirs(new_path, exist_ok = True)

            files = [x for x in Path(labeled).iterdir() if x.is_file()]
            for f in files:
                new_file = os.path.join(new_path, Path(f).stem + "_0_0" + Path(f).suffix)
                print("Move ", f, "to", new_file)
                heket_common.move_file(f, new_file)

    CONN.cursor().execute("""alter table detection_shares add shared text""")
    CONN.cursor().execute("""update detection_shares set shared = cast(detection_id as text)""")
    CONN.cursor().execute("""alter table detection_shares drop column detection_id""")

CONN.commit()
CONN.close()