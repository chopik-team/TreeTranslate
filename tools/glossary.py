"""Explicit local glossary administration. No runtime downloads or automatic learning."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from itertools import islice
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.glossary.engine import GlossaryEngine
from app.glossary.importer import import_terms
from app.glossary.exporter import export_user
from app.glossary.maintenance import stats,integrity,duplicates,conflicts,variant_overlaps,knowledge_conflicts
from app.glossary.packs import install_pack,remove_pack,enable_pack,disable_pack,list_packs
from app.glossary.errors import GlossaryError


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path)
    p.add_argument('action',choices=['list','stats','add','remove','disable','suppress','unsuppress','import','export','install-pack','remove-pack','enable-pack','disable-pack','packs','integrity','duplicates','conflicts'])
    p.add_argument('value',nargs='?');p.add_argument('--target');p.add_argument('--source-language');p.add_argument('--target-language')
    p.add_argument('--domain',default='general');p.add_argument('--trusted',action='store_true');p.add_argument('--limit',type=int,default=100)
    a=p.parse_args();g=GlossaryEngine(a.db)
    if a.action in ('add','suppress','unsuppress') and not all((a.value,a.source_language,a.target_language)):
        p.error('Нужны термин и языковая пара.')
    if a.action=='add' and not a.target:p.error('Нужен --target.')
    if a.action in ('remove','disable','import','export','install-pack','remove-pack','enable-pack','disable-pack') and not a.value:p.error('Нужно значение операции.')
    actions={
      'list':lambda:[asdict(e) for e in islice(g.repository.rows(),max(0,a.limit))],
      'stats':lambda:stats(g),'integrity':lambda:integrity(g.db),'duplicates':lambda:duplicates(g.db),
      'conflicts':lambda:knowledge_conflicts(g),
      'add':lambda:g.remember_term(a.value,a.target,a.source_language,a.target_language,a.domain),
      'remove':lambda:g.repository.remove(int(a.value)),'disable':lambda:g.repository.disable(int(a.value)),
      'suppress':lambda:g.repository.suppress(a.value,a.source_language,a.target_language,a.domain),
      'unsuppress':lambda:g.repository.suppress(a.value,a.source_language,a.target_language,a.domain,enabled=False),
      'import':lambda:import_terms(g.repository,Path(a.value),trusted=a.trusted),
      'export':lambda:export_user(g.repository,Path(a.value)),
      'install-pack':lambda:install_pack(g.db,Path(a.value),trusted=a.trusted),
      'remove-pack':lambda:remove_pack(g.db,a.value),'enable-pack':lambda:enable_pack(g.db,a.value),
      'disable-pack':lambda:disable_pack(g.db,a.value),'packs':lambda:list_packs(g.db),
    }
    try:result=actions[a.action]()
    except (GlossaryError,OSError,ValueError):p.exit(1,'Операция глоссария не выполнена. Проверьте формат и доступность базы.\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
