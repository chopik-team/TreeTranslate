import csv
import json
from pathlib import Path
from .errors import InvalidGlossary


def source_rows(path):
    path=Path(path)
    if path.stat().st_size>512*1024*1024:raise InvalidGlossary('Файл превышает 512 МиБ.')
    with path.open(encoding='utf-8-sig',newline='') as stream:
        if path.suffix.lower() in ('.csv','.tsv'):
            for row in csv.DictReader(stream,delimiter='\t' if path.suffix.lower()=='.tsv' else ','):
                row={k:v for k,v in row.items() if v not in ('',None)}
                row['source_term']=row.pop('source',row.get('source_term',''))
                row['target_term']=row.pop('target',row.get('target_term',''))
                try:
                    if 'priority' in row:row['priority']=int(row['priority'])
                    for k in ('case_sensitive','whole_word'):
                        if k in row:
                            if row[k].lower() not in ('true','false','1','0'):raise ValueError()
                            row[k]=row[k].lower() in ('true','1')
                    for k in ('variants','forbidden_target_variants'):
                        if k in row:row[k]=json.loads(row[k])
                except (ValueError,TypeError):raise InvalidGlossary('Некорректное поле CSV/TSV.') from None
                yield row
        else:
            for line in stream:
                if len(line)>65536:raise InvalidGlossary('Слишком длинная запись.')
                try:yield json.loads(line)
                except ValueError:raise InvalidGlossary('Некорректный JSONL.') from None


def import_terms(repository,path,*,trusted=False):
    def rows():
        for row in source_rows(path):
            if not isinstance(row,dict):raise InvalidGlossary('Ожидается объект записи.')
            row['status']='IMPORTED' if trusted else 'AUTO';row['origin']='user-import';row['source_pack']=''
            yield row
    return repository.insert_many(rows())
