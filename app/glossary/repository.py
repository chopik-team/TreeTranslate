from dataclasses import asdict
from datetime import datetime,timezone
import json
import re
from .models import GlossaryEntry,Status,Mode,TRUST
from .normalization import normalize,key
from .errors import InvalidGlossary


def validate(entry):
    allowed=set(GlossaryEntry.__dataclass_fields__)-{'id','source_normalized','trust','created_at','updated_at'}
    if isinstance(entry,GlossaryEntry):entry={k:v for k,v in asdict(entry).items() if k in allowed}
    if not isinstance(entry,dict) or set(entry)-allowed:raise InvalidGlossary('Неизвестное поле термина.')
    row=asdict(GlossaryEntry(**{k:entry[k] for k in ('source_term','target_term','source_language','target_language')})) if all(k in entry for k in ('source_term','target_term','source_language','target_language')) else None
    if row is None:raise InvalidGlossary('Отсутствуют обязательные поля термина.')
    row.update(entry);row.pop('id')
    for name in ('source_language','target_language'):
        value=row[name]
        if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{2,8})*',value) or value.lower()=='auto':raise InvalidGlossary('Нужна явная языковая пара.')
        row[name]=value.lower()
    for name,limit in [('source_term',256),('target_term',512),('context',512),('notes',2048),('provenance',1024),('origin',128),('source_pack',128)]:
        if not isinstance(row[name],str) or len(row[name])>limit or '\x00' in row[name]:raise InvalidGlossary('Недопустимый текст или длина термина.')
    if not row['source_term'].strip() or not row['target_term'].strip():raise InvalidGlossary('Пустой термин.')
    if not isinstance(row['domain'],str) or not re.fullmatch(r'[a-z][a-z0-9_\-]{0,63}',row['domain']):raise InvalidGlossary('Некорректный domain.')
    if type(row['priority']) is not int or not -10000<=row['priority']<=10000:raise InvalidGlossary('Некорректный приоритет.')
    for name in ('case_sensitive','whole_word'):
        if type(row[name]) is not bool:raise InvalidGlossary('Ожидается логический параметр.')
    try:row['status']=Status(row['status']);row['mode']=Mode(row['mode'])
    except ValueError:raise InvalidGlossary('Неизвестный статус или режим.') from None
    for name in ('variants','forbidden_target_variants'):
        values=row[name]
        if not isinstance(values,(list,tuple)) or len(values)>32 or any(not isinstance(v,str) or not v.strip() or len(v)>256 for v in values):raise InvalidGlossary('Некорректные варианты термина.')
        row[name]=json.dumps(sorted(set(values)),ensure_ascii=False)
    row['source_normalized']=normalize(row['source_term'])
    row['trust']=TRUST[row['status']]
    row['created_at']=row['updated_at']=datetime.now(timezone.utc).isoformat()
    return row


def model(row):
    values=dict(row)
    for name in ('case_sensitive','whole_word'):values[name]=bool(values[name])
    for name in ('variants','forbidden_target_variants'):values[name]=tuple(json.loads(values[name]))
    return GlossaryEntry(**values)


class Repository:
    def __init__(self,db):self.db=db

    def insert_many(self,entries):
        count=0
        with self.db.connect(write=True) as con:
            for entry in entries:
                row=validate(entry)
                keys=list(row)
                values=[row[k] for k in keys]
                existing=con.execute('''SELECT id,status FROM entries WHERE source_language=? AND target_language=? AND source_normalized=?
                    AND target_term=? AND domain=? AND context=? AND case_sensitive=? AND whole_word=? AND mode=?''',
                    [row[k] for k in ('source_language','target_language','source_normalized','target_term','domain','context','case_sensitive','whole_word','mode')]).fetchone()
                if existing:
                    if existing['status'] not in ('REJECTED','DISABLED') and TRUST[row['status']]>TRUST[existing['status']]:
                        con.execute('UPDATE entries SET status=?,trust=?,updated_at=? WHERE id=?',(row['status'],row['trust'],row['updated_at'],existing['id']))
                    continue
                uid=con.execute(f'INSERT INTO entries({",".join(keys)}) VALUES({",".join("?" for _ in keys)})',values).lastrowid
                pair=row['source_language']+'>'+row['target_language']
                for term in {row['source_term'],*json.loads(row['variants'])}:
                    normalized=normalize(term,fold=True)
                    con.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?)',(pair,row['domain'],key(normalized),uid,normalized))
                    con.execute('INSERT OR IGNORE INTO lengths VALUES(?,?,?)',(pair,row['domain'],len(normalized)))
                count+=1
        return count

    def remember_term(self,source_term,target_term,source_language,target_language,domain='general',**kw):
        return self.insert_many([dict(kw,source_term=source_term,target_term=target_term,source_language=source_language,
                                     target_language=target_language,domain=domain,status='CONFIRMED')])

    def disable(self,uid):
        with self.db.connect(write=True) as con:con.execute("UPDATE entries SET status='DISABLED',trust=0 WHERE id=?",(uid,))

    def remove(self,uid):
        with self.db.connect(write=True) as con:con.execute('DELETE FROM entries WHERE id=?',(uid,))

    def suppress(self,source,source_language,target_language,domain='general',*,enabled=True):
        args=(source_language.lower()+'>'+target_language.lower(),domain,normalize(source,fold=True))
        with self.db.connect(write=True) as con:
            if enabled:con.execute('INSERT OR IGNORE INTO suppressions VALUES(?,?,?)',args)
            else:con.execute('DELETE FROM suppressions WHERE pair=? AND domain=? AND source=?',args)

    def rows(self):
        with self.db.connect() as con:
            for row in con.execute('SELECT * FROM entries ORDER BY id'):yield model(row)
