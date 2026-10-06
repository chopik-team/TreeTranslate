from .normalization import mapped,normalize,key,boundary
from .repository import model
from .models import TermMatch
from .errors import ConstraintFailure
from .hot_cache import ABSENT
from functools import lru_cache


def fragments(text,lengths,max_fragments=100000):
    folded,positions=mapped(text,fold=True)
    if sum(max(0,len(folded)-n+1) for n in lengths)>max_fragments:raise ConstraintFailure('lookup_budget')
    hashes={}
    # Work is O(text length * distinct term lengths), never O(dictionary size).
    for length in lengths:
        for start in range(len(folded)-length+1):
            end=start+length
            token=folded[start:end]
            if token!=token.strip():continue
            a,b=positions[start][0],positions[end-1][1]
            if normalize(text[a:b],fold=True)!=token:continue
            hashes.setdefault(key(token),[]).append((a,b,token))
    return hashes


@lru_cache(maxsize=300)
def lexical_statement(size):
    marks=','.join('?' for _ in range(size))
    return f'''SELECT e.*,a.term AS alias FROM aliases a JOIN entries e ON e.id=a.entry_id
        WHERE a.pair=? AND a.domain IN (?,?) AND a.hash IN ({marks}) LIMIT ?'''


def records(con,pair,domain,chunk,limit,cache=None,namespace=()):
    identity=('rows',namespace,pair,domain,tuple(chunk),limit)
    rows=cache.get(identity) if cache is not None else ABSENT
    if rows is ABSENT:
        if cache is not None:cache.stats['sql_queries']+=1
        fetched=con.execute(lexical_statement(len(chunk)),(pair,domain,'general',*chunk,limit+1)).fetchall()
        if len(fetched)>limit:raise ConstraintFailure('candidate_budget')
        rows=[]
        for row in fetched:
            data=dict(row);alias=data.pop('alias');rows.append((model(data),alias))
        rows=tuple(rows)
        if cache is not None:
            size=512+len(repr(identity).encode('utf8'))*2+sum(256+len(repr(entry).encode('utf8'))*3 for entry,alias in rows)
            cache.put(identity,rows,size)
    if len(rows)>limit:raise ConstraintFailure('candidate_budget')
    return rows


def candidates(con,text,pair,domain,context,lengths,store,suppressed,limit,max_fragments=100000,*,lexical_cache=None,namespace=()):
    hashes=fragments(text,lengths,max_fragments)
    values=list(hashes);found=[]
    for offset in range(0,len(values),300):
        chunk=values[offset:offset+300]
        for entry,alias in records(con,pair,domain,chunk,limit,lexical_cache,namespace):
            if entry.status in ('AUTO','REJECTED','DISABLED') or entry.context and entry.context!=context:continue
            if store!='user' and (entry.domain,normalize(entry.source_term,fold=True)) in suppressed:continue
            for a,b,token in hashes[key(alias)]:
                if token!=alias:continue
                original=text[a:b]
                # 孔径 / 孔距 are complete measurement concepts, not a hole
                # label followed by an unrelated suffix. Keep explicit user
                # rules untouched; reject the shorter builtin fragment before
                # longest-match ranking so the complete concept can win.
                if store!='user' and original.endswith('孔') and text[b:b+1] in {'径','距'}:
                    continue
                if entry.case_sensitive and normalize(original) not in {normalize(t) for t in (entry.source_term,*entry.variants)}:continue
                if entry.whole_word and not boundary(text,a,b,original):continue
                found.append(TermMatch(a,b,entry,store))
                if len(found)>limit:raise ConstraintFailure('candidate_budget')
    return found
