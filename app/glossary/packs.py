"""Local immutable SQLite pack payloads; activation lives only in user glossary DB."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile,ZIP_DEFLATED,BadZipFile

from .database import Database
from .repository import Repository,validate
from .errors import InvalidGlossary
from .exporter import portable
from .maintenance import conflicts,duplicates,variant_overlaps

FORMAT='TreeTranslate.tglossary'
MAX_BYTES=512*1024*1024
KNOWN_LICENSES={'CC0-1.0','CC-BY-4.0','CC-BY-SA-4.0','MIT','Apache-2.0','BSD-2-Clause','BSD-3-Clause',
                'GPL-2.0-only','GPL-3.0-only','LGPL-2.1-only','LGPL-3.0-only','ODbL-1.0','PDDL-1.0'}


def validate_manifest(manifest,*,official=False):
    required=('format','schema_version','pack_id','name','version','source_language','target_language','domains',
              'entry_count','created_at','publisher','provenance','license','description','minimum_treetranslate_version','entries_sha256')
    if not isinstance(manifest,dict) or any(k not in manifest for k in required):raise InvalidGlossary('Неполный manifest пакета.')
    if manifest['format']!=FORMAT or manifest['schema_version']!=1:raise InvalidGlossary('Версия пакета не поддерживается.')
    if not isinstance(manifest['pack_id'],str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',manifest['pack_id']):raise InvalidGlossary('Некорректный pack_id.')
    if manifest['pack_id']=='user':raise InvalidGlossary('pack_id зарезервирован.')
    for k in ('version','minimum_treetranslate_version'):
        if not isinstance(manifest[k],str) or not re.fullmatch(r'\d+\.\d+\.\d+',manifest[k]):raise InvalidGlossary('Нужна версия x.y.z.')
    if tuple(map(int,manifest['minimum_treetranslate_version'].split('.')))>(0,7,1):raise InvalidGlossary('Пакет требует более новую TreeTranslate.')
    if type(manifest['entry_count']) is not int or not 0<=manifest['entry_count']<=1000000:raise InvalidGlossary('Некорректное число записей.')
    if not isinstance(manifest['domains'],list) or not manifest['domains']:raise InvalidGlossary('Нужен список domains.')
    if any(not isinstance(domain,str) or not re.fullmatch(r'[a-z][a-z0-9_\-]{0,63}',domain) for domain in manifest['domains']):
        raise InvalidGlossary('Некорректный domain пакета.')
    for k in ('source_language','target_language'):
        language=manifest[k]
        if not isinstance(language,str) or not re.fullmatch(r'[a-z]{2,8}(?:-[a-z0-9]{2,8})*',language) or language=='auto':
            raise InvalidGlossary('Нужна явная языковая пара пакета в нижнем регистре.')
    for k in ('name','publisher','provenance','license','description','created_at'):
        if not isinstance(manifest[k],str) or len(manifest[k])>4096:raise InvalidGlossary('Некорректные метаданные пакета.')
    if official and (manifest['license'] not in KNOWN_LICENSES or manifest['provenance'].strip().lower() in ('','unknown','unspecified') or not manifest['publisher'].strip()):
        raise InvalidGlossary('Официальный пакет требует известную лицензию, источник и издателя.')
    if not isinstance(manifest['entries_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',manifest['entries_sha256']):raise InvalidGlossary('Некорректная контрольная сумма.')


def prepare_rows(rows,manifest,*,trusted):
    for row in rows:
        if not isinstance(row,dict):raise InvalidGlossary('Некорректная запись пакета.')
        row=dict(row)
        if not row.get('provenance'):row['provenance']=manifest['provenance']
        if (row.get('source_language'),row.get('target_language'))!=(manifest['source_language'],manifest['target_language']) or row.get('domain','general') not in manifest['domains']:
            raise InvalidGlossary('Запись не соответствует языкам/domain manifest.')
        row.update(source_pack=manifest['pack_id'],origin='pack',status='BUILTIN' if trusted else 'AUTO')
        yield row


def build_pack(rows,manifest,destination,*,official=True):
    manifest=dict(manifest,format=FORMAT,schema_version=1,entry_count=0,entries_sha256='0'*64)
    validate_manifest(manifest,official=official)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='glossary-build-',dir=destination.parent) as folder:
        db=Database(Path(folder)/'validated.db');repo=Repository(db)
        input_count=0
        def counted():
            nonlocal input_count
            for row in prepare_rows(rows,manifest,trusted=True):input_count+=1;yield row
        repo.insert_many(counted())
        entries=Path(folder)/'entries.jsonl'
        digest=sha256();count=0
        with entries.open('wb') as stream:
            for entry in repo.rows():
                data=(json.dumps(portable(entry),ensure_ascii=False,sort_keys=True)+'\n').encode('utf-8')
                digest.update(data);stream.write(data);count+=1
        manifest.update(entry_count=count,entries_sha256=digest.hexdigest())
        output=Path(folder)/'pack.zip'
        with ZipFile(output,'w',ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,sort_keys=True))
            archive.write(entries,'entries.jsonl')
        report=dict(entries=count,duplicates_removed=input_count-count,conflicts=conflicts(db),variant_overlaps=variant_overlaps(db))
        os.replace(output,destination)
        return report


def install_pack(database,path,*,trusted=False):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise InvalidGlossary('Пакет слишком велик.')
    folder=database.path.parent/'glossary-packs';folder.mkdir(parents=True,exist_ok=True)
    try:
        with ZipFile(path) as archive:
            names=archive.namelist()
            if len(names)!=len(set(names)) or not {'manifest.json','entries.jsonl'}<=set(names) or any(n not in ('manifest.json','entries.jsonl','LICENSE','NOTICE','README') for n in names):
                raise InvalidGlossary('Недопустимые файлы в пакете.')
            if sum(i.file_size for i in archive.infolist())>MAX_BYTES or archive.getinfo('manifest.json').file_size>65536:raise InvalidGlossary('Распакованный пакет слишком велик.')
            manifest=json.loads(archive.read('manifest.json'))
            validate_manifest(manifest)
            with tempfile.TemporaryDirectory(prefix='.install-',dir=folder) as temp:
                payload=Path(temp)/'pack.db';repo=Repository(Database(payload))
                digest=sha256();count=0
                def rows():
                    nonlocal count
                    with archive.open('entries.jsonl') as stream:
                        for line in stream:
                            if len(line)>65536:raise InvalidGlossary('Запись пакета слишком велика.')
                            digest.update(line);count+=1
                            yield json.loads(line)
                repo.insert_many(prepare_rows(rows(),manifest,trusted=trusted))
                if count!=manifest['entry_count'] or digest.hexdigest()!=manifest['entries_sha256']:raise InvalidGlossary('Checksum/count пакета не совпадает.')
                with repo.db.connect() as con:
                    con.commit();con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                # The unique immutable path means active readers never see half an update.
                file_digest=sha256()
                with payload.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):file_digest.update(chunk)
                file_hash=file_digest.hexdigest()
                final=folder/(manifest['pack_id']+'-'+file_hash+'.db')
                if not final.exists():os.replace(payload,final)
                with database.connect(write=True) as con:
                    old=con.execute('SELECT version,enabled FROM packs WHERE pack_id=?',(manifest['pack_id'],)).fetchone()
                    if old and tuple(map(int,manifest['version'].split('.')))<tuple(map(int,old['version'].split('.'))):raise InvalidGlossary('Откат версии пакета запрещён.')
                    enabled=old['enabled'] if old else 1
                    con.execute('INSERT OR REPLACE INTO packs VALUES(?,?,?,?,?)',(manifest['pack_id'],manifest['version'],str(final.resolve()),enabled,json.dumps(manifest,ensure_ascii=False)))
        return dict(pack_id=manifest['pack_id'],version=manifest['version'],entries=count,
                    warning='unknown_license' if manifest['license'] not in KNOWN_LICENSES else None)
    except (BadZipFile,ValueError,UnicodeError,KeyError,TypeError):raise InvalidGlossary('Некорректный пакет; установка отменена.') from None


def enable_pack(database,pack_id,enabled=True):
    with database.connect(write=True) as con:con.execute('UPDATE packs SET enabled=? WHERE pack_id=?',(bool(enabled),pack_id))


def disable_pack(database,pack_id):enable_pack(database,pack_id,False)


def remove_pack(database,pack_id):
    # Payload revisions remain as inert local cache, safe for concurrent readers.
    with database.connect(write=True) as con:con.execute('DELETE FROM packs WHERE pack_id=?',(pack_id,))


def list_packs(database):
    with database.connect() as con:return [dict(r) for r in con.execute('SELECT pack_id,version,enabled,manifest FROM packs ORDER BY pack_id')]
