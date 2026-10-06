from collections import Counter, OrderedDict
import json
import logging
import os
from pathlib import Path
from threading import RLock

from app.config.paths import APP_DATA_DIR, ASSETS_DIR
from app.documents.run_metrics import measure
from .database import Database
from .errors import MemoryError
from .matcher import choose
from .models import Status
from .normalization import digest, normalize, template_key, fuzzy_keys
from .repository import Repository

logger = logging.getLogger('treetranslate.memory')


class TranslationMemoryEngine:
    def __init__(self, path=None, *, builtin_path=None, config=None, warning=None):
        self.config = json.loads((ASSETS_DIR/'config/translation_memory.json').read_text('utf-8'))
        self.config.update(config or {})
        self.db = Database(path or os.environ.get('TREETRANSLATE_TM_PATH') or APP_DATA_DIR/'translation_memory.db',
                           timeout_ms=self.config['busy_timeout_ms'])
        self.repository = Repository(self.db)
        self.builtin = Database(builtin_path, readonly=True) if builtin_path else None
        self.cache = OrderedDict()
        self.lock = RLock()
        self.counters = Counter({key: 0 for key in ('exact_hits', 'normalized_hits', 'placeholder_hits',
                                                    'fuzzy_hits', 'misses', 'reused')})
        self.warning = warning or (lambda message: None)
        self.last_warning = None
        self.disabled = False

    def remember_translation(self, source, corrected_translation, source_language, target_language,
                             domain='general', context='', confirmed=True, **metadata):
        entry = dict(metadata, source_text=source, target_text=corrected_translation,
                     source_language=source_language, target_language=target_language,
                     domain=domain, context=context, status=Status.CONFIRMED if confirmed else Status.AUTO)
        return self.repository.insert_many([entry])[0]

    def remember_template(self, source, target, source_language, target_language, **metadata):
        return self.remember_translation(source, target, source_language, target_language,
                                         is_template=True, **metadata)

    def _failure(self):
        self.disabled = True
        self.last_warning = 'Память переводов временно отключена. Перевод моделями доступен; база сохранена.'
        logger.warning('TM unavailable; model fallback enabled')
        self.warning(self.last_warning)

    def retry(self):
        with self.lock:
            self.disabled = False
            self.db.ready = False
            self.cache.clear()
            self.last_warning = None

    @measure('translation_memory')
    def lookup(self, source, source_language, target_language, domain='general', context=''):
        return self.lookup_many([source], source_language, target_language, domain, context)[0]

    def lookup_many(self, sources, source_language, target_language, domain='general', context=''):
        sources = list(sources)
        pair = (source_language.lower(), target_language.lower())
        if not self.config['enabled'] or self.disabled:
            return [None] * len(sources)
        with self.lock:
            try:
                result = self._lookup_many(sources, pair, domain, context)
            except MemoryError:
                self._failure()
                return [None] * len(sources)
            for match in result:
                self.counters[(match.match_type + '_hits') if match and match.reusable else 'misses'] += 1
            return result

    def _lookup_many(self, sources, pair, domain, context):
        stores = [('user', self.db)] + ([('builtin', self.builtin)] if self.builtin else [])
        revisions = []
        for name, db in stores:
            with db.connect() as con:
                revisions.append((name, con.execute('SELECT revision FROM metadata WHERE id=1').fetchone()[0]))
        generation = (tuple(revisions), tuple(sorted(self.config.items())))
        keys = [(s, pair, domain, context, generation) for s in sources]
        pending = {s for s, key in zip(sources, keys) if key not in self.cache and 0 < len(s) <= 20000}
        candidates = {s: [] for s in pending}
        hashes = {}
        for s in pending:
            for value in {s, normalize(s), (template_key(s) or ('',))[0]}:
                hashes.setdefault(digest(value), set()).add(s)
        values = list(hashes)
        for name, db in stores:
            with db.connect() as con:
                for start in range(0, len(values), 300):
                    chunk = values[start:start+300]
                    marks = ','.join('?' for _ in chunk)
                    # Separate indexed probes, no table-wide OR scan.
                    for column in ('source_hash', 'normalized_hash'):
                        for row in con.execute(f'SELECT * FROM units WHERE source_language=? AND target_language=? AND {column} IN ({marks})', (*pair, *chunk)):
                            for s in hashes[row[column]]:
                                candidates[s].append((row, name))
                if self.config['fuzzy_enabled']:
                    for s in pending:
                        # Exact and normalized candidates do not need a fuzzy search.
                        existing = choose(candidates[s], s, pair, domain, context, self.config)
                        if existing and existing[0].reusable:
                            continue
                        ids = set()
                        limit = max(1, self.config['max_candidates']//6)
                        for key in fuzzy_keys(s):
                            ids.update(r[0] for r in con.execute('SELECT unit_id FROM fuzzy_keys WHERE pair=? AND key=? LIMIT ?', ('>'.join(pair), key, limit)))
                        if ids:
                            for row in con.execute(f'SELECT * FROM units WHERE id IN ({",".join("?" for _ in ids)})', tuple(ids)):
                                candidates[s].append((row, name))
        computed = {}
        for s in pending:
            unique = {(name, row['id']): (row, name) for row, name in candidates[s]}
            matches = choose(unique.values(), s, pair, domain, context, self.config)
            computed[s] = matches[0] if matches else None
        results = []
        for source, key in zip(sources, keys):
            value = self.cache.pop(key) if key in self.cache else computed.get(source)
            results.append(value)
            if self.config['cache_size'] > 0:
                self.cache[key] = value
                while len(self.cache) > self.config['cache_size']:
                    self.cache.popitem(last=False)
        return results

    def record_use(self, match):
        self.counters['reused'] += 1
        if match.store == 'user':
            try:
                self.repository.touch(match.translation_unit_id)
            except MemoryError:
                self._failure()

    def stats(self):
        with self.db.connect() as con:
            statuses = dict(con.execute('SELECT status,count(*) FROM units GROUP BY status'))
            pairs = [tuple(row) for row in con.execute('SELECT source_language,target_language,count(*) FROM units GROUP BY 1,2')]
            domains = dict(con.execute('SELECT domain,count(*) FROM units GROUP BY domain'))
        return dict(total_units=sum(statuses.values()), confirmed_units=statuses.get('CONFIRMED', 0),
                    imported_units=statuses.get('IMPORTED', 0), statuses=statuses, language_pairs=pairs,
                    domains=domains, counters=dict(self.counters), cache_entries=len(self.cache))
