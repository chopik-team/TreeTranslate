"""Deterministic LRU with footprint ceilings and active-reference protection."""
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class Resident:
    value: object
    ram_bytes: int
    vram_bytes: int
    active: int = 0
    inferred: bool = False


class ResidentModelCache:
    def __init__(self, count, ram_bytes, vram_bytes, on_evict=lambda *a: None):
        self.count = max(1, count)
        self.ram_budget = max(0, ram_bytes); self.vram_budget = max(0, vram_bytes)
        self.entries = OrderedDict(); self.on_evict = on_evict
        self.loads = self.reuses = self.evictions = self.maximum = 0

    def footprint(self):
        return (sum(r.ram_bytes for r in self.entries.values()),
                sum(r.vram_bytes for r in self.entries.values()))

    def get(self, key):
        item = self.entries.get(key)
        if item:
            self.entries.move_to_end(key); self.reuses += 1
        return item

    def evict_one(self, reason):
        for key, item in self.entries.items():
            if not item.active:
                del self.entries[key]; self.evictions += 1
                self.on_evict(key, reason)
                return True
        return False

    def make_room(self, ram=0, vram=0):
        while self.entries:
            a,b=self.footprint()
            if len(self.entries)<self.count and a+ram<=self.ram_budget and b+vram<=self.vram_budget:
                return True
            if not self.evict_one('capacity_or_memory'):return False
        return True  # One unavoidable active bundle may exceed a nominal cache budget.

    def put(self, key, value, ram, vram):
        if not self.make_room(ram,vram):
            raise MemoryError('All resident OCR bundles are active')
        item=Resident(value,max(0,ram),max(0,vram))
        self.entries[key]=item;self.loads+=1;self.maximum=max(self.maximum,len(self.entries))
        return item

    def trim(self):
        while self.entries:
            ram,vram=self.footprint()
            if len(self.entries)<=self.count and ram<=self.ram_budget and vram<=self.vram_budget:break
            if not self.evict_one('post_load_memory'):break
