"""Preserve the previous evidence before the authorised diagnostic iteration."""
from pathlib import Path
import json
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aw081_large_zip import production_hashes
QA = ROOT / 'qa/aw081/iterations/15_diagnostic_live_readiness'
QA.mkdir(exist_ok=False)
before = QA / 'before'
before.mkdir()
for relative in ['app/documents/archive_job.py', 'app/documents/job.py',
                 'app/documents/run_metrics.py', 'app/knowledge/directives.py',
                 'app/knowledge/safety.py', 'assets/config/automotive-slot-forms.json',
                 'assets/knowledge/aw083-body-repair-zh-ru.db', 'assets/knowledge/manifest.json',
                 'assets/language-support.json', 'qa/aw081/work_state.json',
                 'docs/AW0.81_LARGE_ZIP_PRERUN_REPORT.md']:
    destination = before / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / relative, destination)
(QA / 'production_before.json').write_text(json.dumps(production_hashes(), indent=2), 'utf8')
print(QA)
