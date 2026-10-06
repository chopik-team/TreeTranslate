"""Bounded immutable-by-copy raw OCR results, keyed by content and semantics."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json


class OCRResultCache:
    def __init__(self, budget):
        self.budget=max(0,budget);self.bytes=0;self.entries=OrderedDict()
        self.hits=self.misses=0

    @staticmethod
    def key(image, command):
        data={k:v for k,v in command.items() if k not in ('device','op','image','resource_plan')}
        data['pixel_sha256']=hashlib.sha256(image.tobytes()).hexdigest()
        data['image_mode']=image.mode;data['image_size']=image.size
        return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=True).encode()).hexdigest()

    def get(self,key,device):
        entry=self.entries.get(key)
        # Cross-device equivalence is unproved: never substitute another device's output.
        if entry and entry[0]['device']==device:
            self.entries.move_to_end(key);self.hits+=1
            return deepcopy(entry[0])
        self.misses+=1;return None

    def put(self,key,value):
        size=len(json.dumps(value,ensure_ascii=True).encode())*3
        if size>self.budget:return
        if key in self.entries:self.bytes-=self.entries.pop(key)[1]
        while self.entries and self.bytes+size>self.budget:
            self.bytes-=self.entries.popitem(last=False)[1][1]
        self.entries[key]=(deepcopy(value),size);self.bytes+=size

    def clear(self):
        self.entries.clear();self.bytes=0
