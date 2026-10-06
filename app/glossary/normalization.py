"""Conservative normalization with offsets into the untouched original string."""
from hashlib import blake2s
import unicodedata
from .hot_cache import ByteLRU,ABSENT

_CACHE=ByteLRU(16*1024**2)

QUOTES=str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"})


def _mapped_uncached(text, *, fold=False):
    pieces=[];spans=[];i=0
    while i<len(text):
        start=i;i+=1
        # Normalize complete combining sequences, retaining their original span.
        while i<len(text) and unicodedata.combining(text[i]):i+=1
        value=unicodedata.normalize('NFKC',text[start:i]).translate(QUOTES)
        if fold:value=value.casefold()
        for char in value:
            char=' ' if char.isspace() else char
            if char==' ' and pieces and pieces[-1]==' ':
                spans[-1]=(spans[-1][0],i)
            else:
                pieces.append(char);spans.append((start,i))
    return ''.join(pieces),spans


def _mapping(text,fold):
    identity=('unicode-nfkc-quotes-whitespace-v1',text,fold)
    value=_CACHE.get(identity)
    if value is ABSENT:
        normalized,spans=_mapped_uncached(text,fold=fold)
        value=normalized,tuple(spans)
        _CACHE.stats['computations']+=1
        if len(text)<=4096:
            _CACHE.put(identity,value,256+len(text.encode('utf8',errors='surrogatepass'))*3+len(normalized.encode('utf8',errors='surrogatepass'))*3+len(spans)*112)
    return value


def mapped(text, *, fold=False):
    normalized,spans=_mapping(text,fold)
    return normalized,list(spans)


def normalize(text, *, fold=False):
    return _mapping(text,fold)[0].strip()


def configure_cache(budget):_CACHE.resize(budget)
def cache_info():return _CACHE.summary()


def key(text):
    return blake2s(text.encode('utf-8'),digest_size=16).hexdigest()


def word(char):
    return char.isalnum() or char=='_' or unicodedata.category(char).startswith('M')


def boundary(text,start,end,term):
    if any('\u3400'<=c<='\u9fff' for c in term):return True
    return (start==0 or not word(text[start-1]) or not word(term[0])) and (end==len(text) or not word(text[end]) or not word(term[-1]))
