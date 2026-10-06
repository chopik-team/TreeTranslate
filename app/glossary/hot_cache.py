"""Byte-bounded lazy LRU. Callers store immutable lexical values only."""
from collections import Counter,OrderedDict
from threading import RLock

ABSENT=object()


class ByteLRU:
    def __init__(self,budget,entries=16384):
        self.budget=max(0,budget);self.limit=entries;self.bytes=0
        self.values=OrderedDict();self.stats=Counter();self.lock=RLock()

    def get(self,key):
        with self.lock:
            row=self.values.get(key)
            if row is None:self.stats['misses']+=1;return ABSENT
            self.values.move_to_end(key)
            self.stats['positive_hits' if row[0] else 'negative_hits']+=1
            return row[0]

    def put(self,key,value,size):
        with self.lock:
            size=max(0,size)
            if size>self.budget or not self.limit:return
            if key in self.values:self.bytes-=self.values.pop(key)[1]
            while self.values and (self.bytes+size>self.budget or len(self.values)>=self.limit):
                self.bytes-=self.values.popitem(last=False)[1][1];self.stats['evictions']+=1
            self.values[key]=(value,size);self.bytes+=size

    def resize(self,budget):
        with self.lock:
            self.budget=max(0,budget)
            while self.values and self.bytes>self.budget:
                self.bytes-=self.values.popitem(last=False)[1][1];self.stats['evictions']+=1

    def clear(self):
        with self.lock:self.values.clear();self.bytes=0

    def summary(self):
        with self.lock:return dict(self.stats,entries=len(self.values),estimated_bytes=self.bytes,budget=self.budget)
