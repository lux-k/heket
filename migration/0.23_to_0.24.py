import sys
from pathlib import Path

parent_dir = str(Path(__file__).resolve().parent.parent)

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import heket_config
import heket_common

#accomodate schema changes...

#all target/non-targets to be defined via class metadata
CONN = heket_common.get_db()
CONN.cursor().execute("""ALTER TABLE species RENAME TO class_metadata""")
CONN.cursor().execute("""alter table class_metadata rename column species_id to class_id""")
CONN.cursor().execute("""alter table class_metadata add target integer not null default 0""")
CONN.commit()
CONN.close()