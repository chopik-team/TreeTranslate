"""Conservative offline domain evidence from the enabled, trusted glossary stores.

Only the compiled terminology index is retained. No request content is cached.
Explicit developer domains bypass this detector; UI requests use the `auto` sentinel.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass

from .normalization import normalize, boundary
from .errors import GlossaryError


@dataclass(frozen=True)
class DomainEvidence:
    domain: str = 'general'
    score: float = 0.0
    matches: int = 0
    margin: float = 0.0


class DomainDetector:
    SAMPLE_LIMIT = 8000
    GENERIC = frozenset('system machine device part control work equipment material metal steel engine '
                        'система машина устройство деталь контроль работа оборудование материал металл сталь двигатель '
                        '系统 机器 设备 控制 工作 材料 金属 钢 发动机'.split())

    def __init__(self, glossary):
        self.glossary = glossary
        self._signature = None
        self._tries = {}

    def _index(self, source, target):
        g = self.glossary
        with g.db.connect() as con:
            stores = g._stores(con)
            suppressed = {(r['domain'], r['source']) for r in con.execute(
                'SELECT domain,source FROM suppressions WHERE pair=?', (source+'>'+target,))}
        revisions = []
        for name, db in stores:
            with db.connect() as con:
                revisions.append((name, str(db.path), con.execute('SELECT revision FROM metadata').fetchone()[0]))
        signature = (source, target, tuple(revisions), tuple(sorted(suppressed)))
        if signature == self._signature:
            return self._tries
        terms = defaultdict(dict)
        for name, db in stores:
            with db.connect() as con:
                rows = con.execute("""SELECT source_term,domain,trust,variants,case_sensitive,whole_word
                    FROM entries WHERE source_language=? AND target_language=? AND domain!='general'
                    AND status IN ('CONFIRMED','REVIEWED','IMPORTED','BUILTIN')
                    AND trust>=0.8 AND context='' AND mode!='FORBIDDEN'""", (source,target))
                for row in rows:
                    term = normalize(row['source_term'], fold=True)
                    if term in self.GENERIC or len(term) < 4:
                        continue
                    if name != 'user' and (row['domain'], term) in suppressed:
                        continue
                    terms[term][row['domain']] = max(row['trust'], terms[term].get(row['domain'],0))
        trie = {}
        for term, domains in terms.items():
            node = trie
            for char in term:
                node = node.setdefault(char,{})
            node[''] = (term, domains)
        self._signature, self._tries = signature, trie
        return trie

    def detect(self, text, source, target):
        g = self.glossary
        if not g or not g.config['enabled'] or g.disabled:
            return DomainEvidence()
        # Spread the bounded sample across long documents, not only their title.
        if len(text) > self.SAMPLE_LIMIT:
            size = self.SAMPLE_LIMIT//3
            text = text[:size]+'\n'+text[len(text)//2:len(text)//2+size]+'\n'+text[-size:]
        text = normalize(text, fold=True)
        with g.lock:
            try:
                trie = self._index(source,target)
            except GlossaryError:
                return DomainEvidence()
        occurrences = Counter()
        metadata = {}
        # Longest evidence per position prevents nested phrases counting as independent terms.
        position = 0
        while position < len(text):
            node = trie; end = position; longest = None
            while end < len(text) and text[end] in node:
                node = node[text[end]]; end += 1
                if '' in node and boundary(text,position,end,text[position:end]):
                    longest = end,node['']
            if longest:
                end,(term,domains) = longest
                occurrences[term] += 1; metadata[term] = domains
                position = end
            else:
                position += 1
        scores = Counter(); counts = Counter()
        for term, count in occurrences.items():
            domains = metadata[term]
            specificity = min(3.0, len(term)/4) / len(domains)
            # Repetition can support evidence but never create independent matches.
            for domain, trust in domains.items():
                scores[domain] += specificity * trust * (1+0.15*min(2,count-1))
                counts[domain] += 1
        ranked = scores.most_common(2)
        if not ranked:
            return DomainEvidence()
        domain, score = ranked[0]; runner = ranked[1][1] if len(ranked)>1 else 0
        margin = score-runner
        accepted = counts[domain]>=2 and score>=4 and margin>=1.5 and (not runner or score/runner>=1.5)
        return DomainEvidence(domain if accepted else 'general',round(score,3),counts[domain],round(margin,3))


def document_sample(segments, limit=8000):
    """Evenly spread bounded evidence including both ends of long paragraphs."""
    count=len(segments)
    if not count:return ''
    slots=min(24,count)
    indexes=sorted({round(i*(count-1)/max(1,slots-1)) for i in range(slots)})
    budget=(limit-slots)//slots
    parts=[]
    for index in indexes:
        text=segments[index].text
        if len(text)>budget:
            size=max(1,budget//3)
            text=text[:size]+' '+text[len(text)//2:len(text)//2+size]+' '+text[-size:]
        parts.append(text)
    return '\n'.join(parts)[:limit]
