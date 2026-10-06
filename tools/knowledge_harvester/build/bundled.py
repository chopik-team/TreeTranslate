"""Explicitly prepare shipped read-only SQLite payloads via the AW0.7.1 installer."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from zipfile import ZipFile
from app.glossary.database import Database
from app.glossary.packs import install_pack, list_packs
from ..provenance import canonical_json, file_hash
from ..models import HarvestError


def prepare(packs, destination, *, dry_run=False):
    destination=Path(destination)
    if destination.exists():raise HarvestError('Bundled output уже существует; выберите новый каталог.')
    paths=sorted(Path(packs).glob('*.tglossary'))
    if dry_run:return {'packs':[p.name for p in paths]}
    if not paths:raise HarvestError('Нет подготовленных пакетов.')
    destination.mkdir(parents=True)
    result=[]
    with tempfile.TemporaryDirectory(prefix='harvest-builtin-') as folder:
        database=Database(Path(folder)/'registry.db')
        for path in paths:install_pack(database,path,trusted=True)
        for row in list_packs(database):
            manifest=json.loads(row['manifest'])
            with database.connect() as con:payload=Path(con.execute('SELECT path FROM packs WHERE pack_id=?',(row['pack_id'],)).fetchone()[0])
            output=destination/(row['pack_id']+'.db');shutil.copyfile(payload,output)
            # Shipped payloads must work in a read-only installation directory.
            # WAL headers otherwise make SQLite try to create -shm/-wal files.
            with sqlite3.connect(output) as connection:
                connection.execute('PRAGMA journal_mode=DELETE')
                if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise HarvestError('Повреждена подготовленная встроенная база.')
            source_pack=next(p for p in paths if p.stem==row['pack_id'])
            notices=destination/(row['pack_id']+'-notices');notices.mkdir()
            with ZipFile(source_pack) as archive:
                for name in ('NOTICE','LICENSE','README'):
                    if name in archive.namelist():
                        with archive.open(name) as source, (notices/name).open('wb') as target:
                            shutil.copyfileobj(source,target,1024*1024)
            result.append(dict(pack_id=row['pack_id'],file=output.name,sha256=file_hash(output),pack_sha256=file_hash(source_pack),
                               notice=(notices/'NOTICE').relative_to(destination).as_posix(),
                               domains=manifest['domains'],source_language=manifest['source_language'],target_language=manifest['target_language'],
                               license=manifest['license'],entries=manifest['entry_count'],preview=True))
    (destination/'manifest.json').write_text(canonical_json({'version':1,'packs':result})+'\n','utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('packs',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args();print(canonical_json(prepare(args.packs,args.output,dry_run=args.dry_run)))
