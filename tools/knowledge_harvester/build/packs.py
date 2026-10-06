from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from app.glossary.packs import build_pack
from app.glossary.normalization import normalize as runtime_normalize
from .. import VERSION
from ..licenses import require_approved
from ..models import HarvestError
from ..provenance import canonical_json, file_hash
from ..config import fingerprint


def _eligible(candidate, sources, config):
    if candidate['status'] != 'VERIFIED' or not candidate['zh'] or not candidate['ru'] or candidate['domain'] not in config['domains']:
        return False
    for evidence in candidate['provenance']:
        require_approved(sources[evidence['source']])
    if len({sources[p['source']]['license'] for p in candidate['provenance']}) != 1:
        raise HarvestError('Смешанные license families требуют отдельной проверки, даже после human review.')
    return True


def _write_member(archive, name, content):
    info = ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, content)


def build_packs(store, config, destination, *, dry_run=False, reverse=False):
    destination = Path(destination)
    with store.connect() as con:
        if reverse and not dry_run:
            # Compare the actual runtime matching keys, including Cyrillic case.
            # Indexed temporary rows avoid a full corpus scan per reverse pair.
            con.execute('CREATE TEMP TABLE reverse_labels(ru TEXT,domain TEXT,zh TEXT)')
            con.executemany('INSERT INTO reverse_labels VALUES(?,?,?)',
                ((runtime_normalize(r['ru'],fold=True),r['domain'],r['zh']) for r in
                 con.execute("SELECT ru,domain,zh FROM candidates WHERE status='VERIFIED'")))
            con.execute('CREATE INDEX reverse_lookup ON reverse_labels(ru,domain,zh)')
        saved = con.execute("SELECT value FROM metadata WHERE key='config_sha256'").fetchone()
        if not saved or saved[0] != fingerprint(config):
            raise HarvestError('Сначала link/classify с текущей policy.')
        revision = con.execute("SELECT value FROM metadata WHERE key='data_revision'").fetchone()
        linked = con.execute("SELECT value FROM metadata WHERE key='linked_revision'").fetchone()
        if (revision[0] if revision else '0') != (linked[0] if linked else '0'):
            raise HarvestError('После ingest требуется повторный link/classify.')
        sources = {r['id']: json.loads(r['metadata']) for r in con.execute('SELECT * FROM sources')}
        groups = set(); skipped = Counter()
        for row in con.execute('SELECT payload FROM candidates ORDER BY id'):
            candidate = json.loads(row[0])
            if _eligible(candidate, sources, config):
                license_id = sources[candidate['provenance'][0]['source']]['license']
                groups.add((candidate['domain'], license_id))
            else:
                skipped[candidate['status']] += 1
        if dry_run:
            return {'groups': sorted(groups), 'skipped': dict(skipped)}
        destination.mkdir(parents=True, exist_ok=True)
        result = []
        commit = subprocess.run(['git','rev-parse','HEAD'], capture_output=True, text=True, check=True).stdout.strip()
        for domain, license_id in sorted(groups):
            for direction in [('zh','ru'), *([('ru','zh')] if reverse else [])]:
                source_language, target_language = direction
                pack_id = domain + '-' + '-'.join(direction) + '-' + license_id.lower().replace('.','-')
                output = destination / (pack_id + '.tglossary')
                if output.exists():
                    raise HarvestError('Pack output уже существует; выберите новый каталог.')
                license_path = Path(__file__).parents[1] / 'license-texts' / (license_id + '.txt')
                if not license_path.is_file():
                    raise HarvestError('Нет сохранённого текста лицензии: ' + license_id)
                with tempfile.TemporaryDirectory(prefix='harvest-pack-', dir=destination) as folder:
                    folder = Path(folder); notice = folder/'NOTICE'; seen_sources = set(); counts = Counter()
                    def entries():
                        # Group only identical normalized source/target/domain; preserve all evidence in NOTICE.
                        with notice.open('w', encoding='utf-8', newline='\n') as metadata:
                            metadata.write(canonical_json({'format':'TreeTranslate.harvest.provenance','version':1,'preview':True})+'\n')
                            for pair in con.execute('SELECT DISTINCT zh,ru FROM candidates WHERE domain=? AND status=? ORDER BY zh,ru', (domain,'VERIFIED')):
                                members = []
                                for row in con.execute('SELECT payload FROM candidates WHERE zh=? AND ru=? AND domain=? AND status=? ORDER BY id LIMIT 129', (*pair,domain,'VERIFIED')):
                                    candidate = json.loads(row[0])
                                    if _eligible(candidate,sources,config) and sources[candidate['provenance'][0]['source']]['license'] == license_id:
                                        members.append(candidate)
                                if not members:
                                    continue
                                if source_language == 'ru':
                                    alternatives=con.execute('SELECT count(DISTINCT zh) FROM reverse_labels WHERE ru=? AND domain=?', (runtime_normalize(pair['ru'],fold=True),domain)).fetchone()[0]
                                    if alternatives>1:
                                        counts['reverse_conflicts_rejected'] += len(members); continue
                                if len(members)>128:
                                    counts['merge_limit_rejected'] += len(members); continue
                                first = members[0]
                                key, target = ('zh','ru') if source_language == 'zh' else ('ru','zh')
                                variants = sorted({v for m in members for v in [m[key],*m[key+'_variants']]}-{first[key]})
                                if source_language == 'ru':
                                    # Forward alias conflicts do not prove reverse aliases safe.
                                    # Keep them in NOTICE for review, not in runtime matching.
                                    counts['reverse_aliases_withheld'] += len(variants)
                                    variants = []
                                if len(variants)>32:
                                    counts['variant_limit_rejected'] += len(members); continue
                                for member in members:
                                    metadata.write(canonical_json(member)+'\n')
                                    seen_sources.update(p['source'] for p in member['provenance'])
                                    counts[member['link_type']] += 1
                                    counts['manually_reviewed'] += member['manual_review']
                                counts['accepted_entries'] += 1; counts['duplicate_pairs_merged'] += len(members)-1
                                yield dict(source_term=first[key],target_term=first[target],source_language=source_language,
                                    target_language=target_language,domain=domain,case_sensitive=True,whole_word=True,
                                    priority=0,mode='PREFERRED',variants=variants,status='BUILTIN',
                                    provenance='harvest:'+first['id']+'; full evidence: NOTICE',notes='DEVELOPER PREVIEW; concept '+first['concept'][:100])
                            metadata.write(canonical_json({'sources':{k:sources[k] for k in sorted(seen_sources)}})+'\n')
                    # Input-derived fixed date; ZIP member times are normalized below.
                    manifest = dict(pack_id=pack_id,name=domain+' ZH/RU — DEVELOPER PREVIEW',version=VERSION,
                        source_language=source_language,target_language=target_language,domains=[domain],
                        created_at=max(s['acquired_at'] for s in sources.values()),publisher='CHOPIK Team',
                        provenance='Harvest '+VERSION+'; config SHA256 '+fingerprint(config)+'; git '+commit,
                        license=license_id,description='Source-derived technical terms; developer preview, not human-certified.',
                        minimum_treetranslate_version='0.7.1')
                    base = folder/'base.tglossary'; build_pack(entries(),manifest,base,official=True)
                    final = folder/'final.tglossary'
                    with ZipFile(base) as original, ZipFile(final,'w',ZIP_DEFLATED) as archive:
                        for name in ('manifest.json','entries.jsonl'):
                            # Copy in chunks with normalized ZIP metadata; no full corpus in RAM.
                            info=ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED;info.external_attr=0o644<<16
                            with original.open(name) as src, archive.open(info,'w') as dst:
                                while chunk:=src.read(1024*1024):dst.write(chunk)
                        for name,path in [('NOTICE',notice),('LICENSE',license_path)]:
                            info=ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED;info.external_attr=0o644<<16
                            with path.open('rb') as src,archive.open(info,'w') as dst:
                                while chunk:=src.read(1024*1024):dst.write(chunk)
                        _write_member(archive,'README','DEVELOPER PREVIEW\nSource records were normalized, classified and aligned by concept.\nNOTICE is JSONL: candidate provenance followed by source metadata. No endorsement by upstream.\n')
                    os.replace(final,output)
                    item=dict(pack_id=pack_id,domain=domain,license=license_id,sha256=file_hash(output),bytes=output.stat().st_size,
                              sources=sorted(seen_sources),counts=dict(counts),preview=True)
                    output.with_suffix('.report.json').write_text(canonical_json(item)+'\n','utf-8');result.append(item)
        (destination/'packs.json').write_text(canonical_json({'packs':result,'skipped_candidates':dict(skipped),'empty_domains':sorted(set(config['domains'])-{r['domain'] for r in result})})+'\n','utf-8')
        return result
