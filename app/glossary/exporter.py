from dataclasses import asdict
import json
from app.translation_memory.exporter import atomic_text


def portable(entry):
    return {k:v for k,v in asdict(entry).items() if k not in ('id','source_normalized','trust','created_at','updated_at')}


def export_user(repository,path):
    count=0
    with atomic_text(path) as stream:
        for entry in repository.rows():
            # Only the writable user repository; never traverse installed pack stores.
            stream.write(json.dumps(portable(entry),ensure_ascii=False)+'\n');count+=1
    return count
