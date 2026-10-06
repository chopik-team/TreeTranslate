"""Bounded document-stage execution. No translation or resource-quality policy."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextvars import copy_context
from dataclasses import dataclass, field, asdict
from enum import Enum
from threading import Lock, Event
from time import perf_counter
from contextlib import contextmanager
import os
import psutil

from app.engine.errors import TranslationCancelledError

GIB = 1024**3
MIB = 1024**2


class SchedulePolicy(str, Enum):
    ORIGINAL = 'original'
    EASY_FIRST = 'easy_first'


@dataclass(frozen=True)
class PipelineCapabilities:
    logical_cpus: int
    physical_cpus: int
    ram_total: int
    ram_available: int
    cuda: bool = False
    vram_total: int = 0
    vram_free: int = 0
    ocr_resident_bytes: int = 0
    nmt_resident_bytes: int = 0
    memory_pressure: float = 0.

    @classmethod
    def detect(cls):
        from app.ocr.runtime.hardware_plan import OCRCapabilities
        c = OCRCapabilities.detect('gpu')
        # Existing runtime owns resident models. Do not initialize CUDA merely
        # to schedule CPU work. Footprints are conservative admission reserves.
        return cls(c.logical_threads, psutil.cpu_count(logical=False) or 1,
            c.ram_total, c.ram_available, c.cuda, c.vram_total, c.vram_available,
            768*MIB, 2*GIB, psutil.virtual_memory().percent/100)


@dataclass(frozen=True)
class PipelineHardwarePlan:
    prepare_workers: int
    semantic_workers: int
    depth: int
    ready_depth: int
    writer_depth: int
    max_prepared_bytes: int
    max_inflight_bytes: int
    ram_reserve_bytes: int
    cpu_headroom: int
    gpu_owners: int = 1

    @classmethod
    def build(cls, c, *, proven_depth=2):
        total = max(0, c.ram_total)
        reserve = min(total, max(2*GIB, total//6))
        available = min(total, max(0, c.ram_available))
        resident = max(0, c.ocr_resident_bytes)+max(0, c.nmt_resident_bytes)
        usable = max(0, available-reserve-resident)
        budget = min(total//10, usable//3)
        cpu = max(1, c.logical_cpus)
        headroom = max(1, cpu//8)
        capacity = min(max(1, proven_depth), max(1, cpu-headroom-1),
                       max(1, (cpu-headroom)//3),
                       max(1, budget//(192*MIB)))
        gpu_usable = max(0, min(max(0,c.vram_total), max(0,c.vram_free))-
                         max(512*MIB, max(0,c.vram_total)//8))
        if c.cuda and gpu_usable < max(max(0,c.ocr_resident_bytes), max(0,c.nmt_resident_bytes)):
            capacity = 1
        if cpu <= 4 or not c.cuda or c.memory_pressure >= .85:
            capacity = 1
        elif c.memory_pressure >= .70:
            capacity = min(capacity, 2)
        return cls(1, 1, capacity, capacity, 1,
                   budget, budget, reserve, headroom)

    def as_dict(self):
        return asdict(self)


@dataclass
class WorkItem:
    sequence_id: int
    source: object
    estimated_bytes: int
    cheap_size: int = 0
    current_bytes: int = 0
    context: object = field(default_factory=copy_context)
    value: object = None
    error: BaseException | None = None


class GpuAdmission:
    """OCR before_ocr/model release and NMT use the same execution owner."""
    def __init__(self, checkpoint, metrics):
        self.lock = Lock()
        self._state_lock = Lock()
        self._busy_seconds = 0.
        self._busy_started = None
        self.checkpoint, self.metrics = checkpoint, metrics

    @contextmanager
    def own(self, kind):
        start = perf_counter()
        while not self.lock.acquire(timeout=.1):
            self.checkpoint()
        self.metrics[kind+'_admission_wait_seconds'] += perf_counter()-start
        with self._state_lock:
            self._busy_started = perf_counter()
        try:
            self.checkpoint()
            yield
        finally:
            with self._state_lock:
                self._busy_seconds += perf_counter()-self._busy_started
                self._busy_started = None
            self.lock.release()

    def busy_seconds(self):
        with self._state_lock:
            return self._busy_seconds+(perf_counter()-self._busy_started if self._busy_started is not None else 0.)

    def router(self, **kwargs):
        from app.ocr.router.ocr_router import OcrRouter
        gate = self
        class AdmittedRouter(OcrRouter):
            def recognize(self, request):
                with gate.own('ocr'):
                    return super().recognize(request)
        return AdmittedRouter(**kwargs)


class StagedPipeline:
    """One prepare reader, one semantic owner, one writer, canonical commit.

    Admission leases are held until commit, including failed items. The sliding
    inventory window bounds both futures and out-of-order results. Executors
    never receive more than depth work items; cancellation joins both workers.
    """
    def __init__(self, plan, control, policy=SchedulePolicy.ORIGINAL, pressure=None):
        from collections import Counter
        self.plan, self.control = plan, control
        self.policy = SchedulePolicy(policy)
        self.pressure = pressure or (lambda: psutil.virtual_memory().percent/100)
        self.stop = Event()
        self.metrics = Counter()
        self.gpu = GpuAdmission(self.checkpoint, self.metrics)

    def checkpoint(self):
        if self.stop.is_set():
            raise TranslationCancelledError()
        self.control.checkpoint()

    def _wait(self, future, counter):
        start = perf_counter()
        gpu_busy = self.gpu.busy_seconds()
        try:
            while True:
                self.checkpoint()
                try:
                    return future.result(timeout=.1)
                except TimeoutError:
                    continue
        finally:
            elapsed = perf_counter()-start
            self.metrics[counter] += elapsed
            if counter == 'gpu_waiting_ready_seconds':
                self.metrics['gpu_idle_waiting_ready_seconds'] += max(0., elapsed-(self.gpu.busy_seconds()-gpu_busy))

    def run(self, items, prepare, translate, write, commit, cleanup=lambda item: None):
        items = iter(items)
        active = []
        prepared = {}
        written = {}
        translated = set()
        exhausted = False
        bytes_used = 0
        last_writer = perf_counter()
        blocked_since = None
        prepare_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='tt-prepare')
        writer_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='tt-writer')
        lookahead = None
        first_ready = Event()
        first_sequence = None

        def stage(item, callback):
            self.checkpoint()
            try:
                if item.error is None:
                    item.value = callback(item)
            except (TranslationCancelledError, MemoryError, OSError) as error:
                raise
            except Exception as error:
                # SourceChangedError is classified by archive commit and never
                # silently converted to a preserved child.
                item.error = error
            return item

        def writer_stage(item):
            nonlocal last_writer
            self.metrics['writer_waiting_seconds'] += perf_counter()-last_writer
            try:
                return stage(item, write)
            finally:
                last_writer = perf_counter()
                if item.sequence_id == first_sequence:
                    first_ready.set()

        def prepare_stage(item):
            # The optional easy-first policy gives its cheap first document a
            # complete writer turn before the next PDF can hold PDF_LOCK during
            # OCR. Otherwise speculative heavy prepare defeats early readiness.
            if self.policy == SchedulePolicy.EASY_FIRST and item.sequence_id != first_sequence:
                while not first_ready.wait(.1):
                    self.checkpoint()
            return stage(item, prepare)

        try:
            while not exhausted or active or lookahead is not None:
                self.checkpoint()
                pressure_depth = 1 if self.pressure() >= .85 else self.plan.depth
                admitted = []
                while not exhausted and len(active) < pressure_depth:
                    if lookahead is None:
                        try:
                            lookahead = next(items)
                        except StopIteration:
                            exhausted = True
                            break
                    estimate = max(0, lookahead.estimated_bytes)
                    if active and bytes_used+estimate > self.plan.max_inflight_bytes:
                        break
                    # An individually oversized document retains the serial
                    # recovery path; never enlarge the concurrent memory budget.
                    lookahead.serial = estimate > self.plan.max_inflight_bytes
                    if lookahead.serial and active:
                        break
                    item = lookahead
                    lookahead = None
                    active.append(item)
                    admitted.append(item)
                    bytes_used += estimate
                    self.metrics['inflight_high_water'] = max(self.metrics['inflight_high_water'], len(active))
                    self.metrics['estimated_bytes_high_water'] = max(self.metrics['estimated_bytes_high_water'], bytes_used)
                    if item.serial:
                        break
                if admitted:
                    ordered = sorted(admitted, key=lambda i: (i.cheap_size, i.sequence_id)) if self.policy == SchedulePolicy.EASY_FIRST else admitted
                    if first_sequence is None:
                        first_sequence = ordered[0].sequence_id
                    for item in ordered:
                        if item.serial:
                            # Use the current owner, without concurrent prepared IR.
                            item.context.run(stage, item, prepare)
                            from concurrent.futures import Future
                            future = Future(); future.set_result(item)
                            prepared[item.sequence_id] = future
                        else:
                            prepared[item.sequence_id] = prepare_pool.submit(item.context.run, prepare_stage, item)
                    self.metrics['ready_high_water'] = max(self.metrics['ready_high_water'], len(prepared))
                if blocked_since is not None and len(active) < pressure_depth and lookahead is None:
                    self.metrics['prepare_backpressure_seconds'] += perf_counter()-blocked_since
                    blocked_since = None
                if blocked_since is None and not exhausted and (len(active) >= pressure_depth or lookahead is not None):
                    blocked_since = perf_counter()
                eligible = [i for i in active if i.sequence_id not in translated]
                if eligible:
                    if self.policy == SchedulePolicy.EASY_FIRST:
                        eligible.sort(key=lambda i: (i.cheap_size, i.sequence_id))
                    item = eligible[0]
                    future = prepared.pop(item.sequence_id)
                    self._wait(future, 'gpu_waiting_ready_seconds')
                    self.metrics['current_bytes_high_water'] = max(self.metrics['current_bytes_high_water'], sum(i.current_bytes for i in active))
                    if getattr(item, 'requires_serial', False):
                        # An unexpectedly large IR was discarded by prepare.
                        # Drain readers before reopening on the owner, so no
                        # reader can hold PDF_LOCK while awaiting its GPU gate.
                        first_ready.set()
                        for pending in prepared.values():
                            self._wait(pending, 'prepare_backpressure_seconds')
                        item.context.run(stage, item, translate)
                    else:
                        with self.gpu.own('nmt'):
                            item.context.run(stage, item, translate)
                    outstanding_writes = [f for f in written.values() if not f.done()]
                    if len(outstanding_writes) >= self.plan.writer_depth+1:
                        self._wait(outstanding_writes[0], 'writer_queue_backpressure_seconds')
                    written[item.sequence_id] = writer_pool.submit(item.context.run, writer_stage, item)
                    translated.add(item.sequence_id)
                    self.metrics['writer_high_water'] = max(self.metrics['writer_high_water'], sum(not f.done() for f in written.values()))
                while active and active[0].sequence_id in written:
                    item = active[0]
                    future = written[item.sequence_id]
                    if eligible and not future.done() and any(i.sequence_id not in translated for i in active):
                        break
                    self._wait(future, 'archive_waiting_result_seconds')
                    item.context.run(commit, item)
                    item.context.run(cleanup, item)
                    self.metrics['committed_items'] += 1
                    bytes_used -= max(0, item.estimated_bytes)
                    translated.remove(item.sequence_id)
                    written.pop(item.sequence_id)
                    active.pop(0)
                if blocked_since is not None and len(active) < pressure_depth and (lookahead is None or bytes_used+lookahead.estimated_bytes <= self.plan.max_inflight_bytes):
                    self.metrics['prepare_backpressure_seconds'] += perf_counter()-blocked_since
                    blocked_since = None
        except BaseException:
            self.stop.set()
            # Wake paused workers too. Preserve the original exception for the
            # archive fatal/cancellation policy instead of masking it on join.
            self.control.cancel()
            raise
        finally:
            if blocked_since is not None:
                self.metrics['prepare_backpressure_seconds'] += perf_counter()-blocked_since
            self.stop.set()
            prepare_pool.shutdown(wait=True, cancel_futures=True)
            writer_pool.shutdown(wait=True, cancel_futures=True)
            for item in active:
                item.context.run(cleanup, item)
            self.metrics['remaining_inflight'] = 0
            self.metrics['workers_joined'] = 1
