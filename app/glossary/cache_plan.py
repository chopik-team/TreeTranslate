"""Memory ceilings for data access; no terminology or matching policy."""
from dataclasses import dataclass
import psutil

MIB=1024**2
GIB=1024**3


@dataclass(frozen=True)
class GlossaryCachePlan:
    lexical_bytes: int
    normalization_bytes: int
    document_prefetch_bytes: int
    prefetch_batch_items: int
    reserve_bytes: int

    @classmethod
    def build(cls,total,available,process_bytes,db_bytes,working_set_bytes):
        total=max(0,total);available=min(total,max(0,available))
        reserve=min(total,max(2*GIB,int(total*.15)))
        usable=max(0,available-reserve)
        # A process near the physical-memory ceiling must give back caches.
        if process_bytes>max(0,total-reserve):usable=0
        lexical=min(256*MIB,usable//32,max(0,working_set_bytes),max(0,db_bytes)*2)
        normalization=min(32*MIB,usable//256)
        prefetch=min(16*MIB,lexical//4,usable//512)
        batch=min(256,max(1,prefetch//(64*1024))) if prefetch else 0
        return cls(lexical,normalization,prefetch,batch,reserve)

    @classmethod
    def detect(cls,db_bytes,working_set_bytes=256*MIB):
        memory=psutil.virtual_memory()
        return cls.build(memory.total,memory.available,psutil.Process().memory_info().rss,
                         db_bytes,working_set_bytes)
