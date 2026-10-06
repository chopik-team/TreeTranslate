"""Reuse AW086 production capture with separate, immutable QA destinations."""
import json
from pathlib import Path
import shutil
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import aw086_e2e as capture
from app.glossary.bundled import bundled_paths
from tools.aw087_build import QA,PACK

if __name__=='__main__':
    mode=sys.argv[1];capture.QA=QA
    if mode=='baseline':
        capture.QA=QA/'baseline';capture.QA.mkdir(exist_ok=True)
        clone=capture.QA/'aw086-curated.db'
        if not clone.exists():
            shutil.copy2(PACK,clone)
            with sqlite3.connect(clone) as con:
                con.execute("DELETE FROM knowledge_context_index WHERE entry_id IN (SELECT id FROM entries WHERE json_extract(notes,'$.context_version')='0.8.7')")
                con.execute("DELETE FROM aliases WHERE entry_id IN (SELECT id FROM entries WHERE json_extract(notes,'$.context_version')='0.8.7')")
                con.execute("DELETE FROM entries WHERE json_extract(notes,'$.context_version')='0.8.7'")
                assert con.execute('SELECT COUNT(*) FROM entries').fetchone()[0]==301
        paths=[clone if Path(p).resolve()==PACK.resolve() else p for p in bundled_paths()]
        capture.run('coolant',cycle='aw087-baseline',capture_routes=True,paths_override=paths,legacy_templates=True)
    else:capture.run(mode,cycle='aw087',capture_routes=True)
