"""Reproduce layout blockers without changing immutable AW088 QA."""
import json
import sys
from pathlib import Path
from hashlib import sha256
from dataclasses import asdict
from zipfile import ZipFile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QA = ROOT / 'qa/aw081'


def run(stage):
    from tools.aw088_prepare import ZIP
    from app.documents.pdf_document import PdfDocument
    old = json.loads((ROOT / 'qa/aw088/representative_holdout.json').read_text('utf8'))
    work = QA / 'pdf_blockers'
    work.mkdir(exist_ok=True)
    records = []
    with ZipFile(ZIP) as archive:
        for index in [10, 16]:
            item = old['documents'][index]
            data = archive.read(item['member'])
            assert sha256(data).hexdigest() == item['sha256']
            source = work / f'original-{index}.pdf'
            source.write_bytes(data)
            record = dict(index=index, member=item['member'], sha256=item['sha256'])
            router = None
            try:
                extractor = None
                if stage == 'after' and index == 10:
                    from app.ocr.pdf_extractor import HybridPdfExtractor
                    from app.ocr.router.ocr_router import OcrRouter
                    from app.documents.job import DocumentConfig
                    router = OcrRouter()
                    extractor = HybridPdfExtractor(router, DocumentConfig(source='zh', target='ru'))
                document = PdfDocument(source, extractor=extractor)
                record['segments'] = [asdict(s) for s in document.segments]
                for segment in document.segments:
                    segment.translated = segment.text
                output = work / f'{stage}-preserved-{index}.pdf'
                document.write(output)
                document.validate(output)
                document.assert_source_unchanged()
                record.update(validation='PASS', output=str(output), pages=len(document.pages))
                if extractor:
                    record['ocr_timings'] = extractor.timings
                    record['ocr_segments'] = sum(s.origin == 'ocr' for s in document.segments)
            except Exception as error:
                record.update(validation='FAILED', error=type(error).__name__, message=str(error))
            finally:
                if router:
                    router.runtime.shutdown()
            records.append(record)
    (QA / f'pdf_blockers_{stage}.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), 'utf8')
    print([(r['index'], r['validation'], r.get('message')) for r in records], flush=True)


if __name__ == '__main__':
    run(sys.argv[1])
