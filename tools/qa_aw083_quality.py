"""Rebuild authored terminology and permanent gold; never download resources."""
import json
import re
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QA = ROOT / 'qa/aw083'
from app.documents.pdf_ocr_policy import classify, protected_kind
from app.documents.pdf_types import PdfSegment
from app.glossary.database import Database
from app.glossary.repository import Repository


def terms():
    pairs = dict(line.split('\t', 1) for line in (QA/'canonical_terms.tsv').read_text('utf-8').splitlines() if line.strip())
    pairs['本图中所示的这些尺寸值为实际测量的尺寸值。'] = 'Размеры, указанные на данном рисунке, являются фактически измеренными значениями.'
    pairs['*本图中所示的这些尺寸值为实际测量的尺寸值。 [ 单位： mm(inch) ]'] = '*Размеры, указанные на данном рисунке, являются фактически измеренными значениями. [Единицы: мм (дюймы)]'
    pairs['本图中所示的这些尺寸值为实际测量的尺寸值。\n[单位：mm (inch)]'] = 'Размеры, указанные на данном рисунке, являются фактически измеренными значениями.\n[Единицы: мм (дюймы)]'
    return pairs


def build():
    pairs = terms()
    destination = ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db'
    # Idempotent insertion using the existing schema; never touch user knowledge.
    repo = Repository(Database(destination))
    repo.insert_many(dict(source_term=s, target_term=t, source_language='zh', target_language='ru',
        domain='automotive', status='BUILTIN', priority=100, origin='builtin',
        source_pack='aw083-body-repair', provenance='User-approved AW0.8.3 seeds and authored technical terminology; QA references are separate')
        for s,t in pairs.items())
    with repo.db.connect(write=True) as con:
        con.commit()
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    path = ROOT/'assets/knowledge/manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    manifest['packs'] = [p for p in manifest['packs'] if p.get('pack_id') != 'aw083-body-repair']
    manifest['packs'].append(dict(file=destination.name, sha256=sha256(destination.read_bytes()).hexdigest(),
        pack_id='aw083-body-repair', domains=['automotive'], entries=len(pairs),
        source_language='zh', target_language='ru', license='Authored terminology; no OEM document redistribution',
        notice='Contains user-approved terminology and independently authored translations, not source PDF content.'))
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n','utf-8')
    baseline = json.loads((QA/'baseline_segments.json').read_text('utf-8'))
    documents = []
    for document in baseline['documents']:
        samples = []
        for s in document['segments']:
            source = s['text']
            semantic = []
            occupied = []
            for term in sorted(pairs, key=len, reverse=True):
                for match in re.finditer(re.escape(term), source):
                    if not any(match.start()<b and match.end()>a for a,b in occupied):
                        semantic.append(dict(source=term, expected=pairs[term]))
                        occupied.append((match.start(),match.end()))
            values = re.findall(r"[Øø]?\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)*|(?<![A-Za-z])[A-Z]['′″\"]*(?:[-/=][A-Z]['′″\"]*)*(?![A-Za-z])", source)
            block = PdfSegment(**s)
            samples.append(dict(page=s['page'], block_id=s['block_id'], source=source, origin=s['origin'],
                ocr_kind=classify(block) if s['origin']=='ocr' else '', critical_terms=semantic,
                protected_values=values))
        documents.append(dict(file=document['file'], source_pages=document['source_pages'], samples=samples))
    gold = dict(version=1, purpose='Evaluation only; never loaded by the production translator',
        source_sha256=baseline['source_hash_before'], canonical_terms=pairs,
        names={s:t for s,t in pairs.items() if s in {'车身尺寸','一般事项','车身维修','内部','前车身','后车身','车身侧面','车身底部','车身面板间隙'}},
        documents=documents, protected_examples=["A", "A'", 'A″', "B'", "H'", "R-R'", 'T-U', 'BIW', 'VIN', 'ITM', 'GDS', 'ECU', 'Ø6.6', 'Ø13', '7x12', '8.5x8.5', '3.5 ± 0.5 mm', '548 (21.59)', 'A-B: 548 (21.59)'],
        instructions=[dict(source=s['text'], baseline=s['translated'], review='Manual semantic evaluation required; no full-document production lookup')
            for s in baseline['documents'][0]['segments'] if re.match(r'^[1-9]\.',s['text'])])
    references = [
        'Эти измеренные значения приведены только как ориентир для послепродажного обслуживания A/S; использовать их как технические нормативы нельзя.',
        'Как правило, все измерения в этом руководстве выполняются кузовной измерительной линейкой.',
        'При использовании рулетки убедитесь, что она не растянута, не перекручена и не согнута.',
        'Для измерения размеров кузова в этом руководстве используются проекционные и фактические размеры.',
        'Проекционные размеры получают проецированием точек измерения на опорную плоскость; они служат базовыми размерами для оценки изменения геометрии кузова.',
        'Если длина измерительного наконечника регулируется, удлините его на величину разницы высот между двумя поверхностями и выполните измерение.',
        'Фактический размер — прямое расстояние между точками измерения; он служит ориентиром при измерении кузовной линейкой.',
        "Сначала установите одинаковую длину обоих измерительных наконечников (A=A'), затем выполните измерение.",
    ]
    references.append('Выполняйте измерение по центру отверстия.')
    for item in gold['instructions']:item['expected']=references[int(item['source'][0])-1]
    gold['semantic_review_cases'] = [dict(file='一般事项.pdf',source=s['source'],expected=s['expected']) for s in gold['instructions']]
    gold['semantic_review_cases'] += [dict(file='一般事项.pdf',source='检查探头和量规,确保无自 由间隙。',
        expected='Проверьте измерительные наконечники и линейку: люфта быть не должно.')]
    (QA/'body_dimensions_gold.json').write_text(json.dumps(gold,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('Authored terms',len(pairs),'gold documents',len(documents))


if __name__ == '__main__':
    build()
