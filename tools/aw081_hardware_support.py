"""Temporary QA monitoring/budgets. Never imported by application entry points."""
from collections import Counter
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
from threading import Event, Thread
from time import perf_counter
import psutil

GIB = 1024 ** 3
NVSMI = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/nvidia-smi.exe'


class BasicLimit(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
        ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
        ('active_processes', wintypes.DWORD), ('affinity', ctypes.c_size_t),
        ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
        ('read_operations', 'write_operations', 'other_operations', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimit(ctypes.Structure):
    _fields_ = [('basic', BasicLimit), ('io', IoCounters)] + [(name, ctypes.c_size_t) for name in
        ('process_memory', 'job_memory', 'peak_process_memory', 'peak_job_memory')]


class CommitBudget:
    """Windows job-wide COMMIT cap, explicitly not a physical RSS reservation."""
    def __init__(self, gib):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        k = self.kernel
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.GetCurrentProcess.restype = wintypes.HANDLE
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
        limit = ExtendedLimit(); limit.basic.flags = 0x200; limit.job_memory = int(gib * GIB)
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(limit), ctypes.sizeof(limit)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not k.AssignProcessToJobObject(self.handle, k.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())

    def peak(self):
        limit = ExtendedLimit()
        if not self.kernel.QueryInformationJobObject(self.handle, 9, ctypes.byref(limit), ctypes.sizeof(limit), None):
            return None
        return limit.peak_job_memory


def gpu_once():
    if not NVSMI.is_file(): return None
    fields = 'name,memory.total,memory.used,utilization.gpu,temperature.gpu,clocks.current.sm,power.draw'
    result = subprocess.run([str(NVSMI), '--query-gpu=' + fields, '--format=csv,noheader,nounits'],
        capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode: return None
    row = [value.strip() for value in result.stdout.splitlines()[0].split(',')]
    return dict(name=row[0], total_mib=float(row[1]), used_mib=float(row[2]), utilization=float(row[3]),
        temperature_c=float(row[4]), clock_mhz=float(row[5]), power_w=float(row[6]))


class Monitor:
    """One-second tree CPU/RSS plus persistent device-wide nvidia-smi stream."""
    def __init__(self, path, budget, state):
        self.path, self.budget, self.state = path, budget, state
        self.stop = Event(); self.records = []; self.cpu_times = {}; self.last_cpu = 0.
        self.gpu = None; self.nvprocess = None; self.errors = []

    def start(self):
        self.started = perf_counter()
        p = psutil.Process()
        for child in [p] + p.children(recursive=True):
            try:
                c = child.cpu_times(); self.cpu_times[(child.pid, child.create_time())] = c.user+c.system
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        self.initial_cpu = sum(self.cpu_times.values()); self.last_cpu = self.initial_cpu
        if NVSMI.is_file():
            fields = 'memory.used,utilization.gpu,temperature.gpu,clocks.current.sm,power.draw'
            self.nvprocess = subprocess.Popen([str(NVSMI), '--query-gpu=' + fields,
                '--format=csv,noheader,nounits', '--loop=1'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            def read_gpu():
                for line in self.nvprocess.stdout:
                    try:
                        values = [float(x.strip()) for x in line.split(',')]
                        self.gpu = dict(zip(['used_mib', 'utilization', 'temperature_c', 'clock_mhz', 'power_w'], values))
                    except (ValueError, TypeError): pass
            self.gpu_thread = Thread(target=read_gpu, daemon=True); self.gpu_thread.start()
        self.thread = Thread(target=self._loop, daemon=True); self.thread.start()

    def _loop(self):
        process = psutil.Process(); last = perf_counter(); psutil.cpu_percent(None)
        with self.path.open('x', encoding='utf8') as stream:
            while not self.stop.is_set():
                try:
                    tree = [process] + process.children(recursive=True)
                    rss = commit = faults = 0; children = []
                    for p in tree:
                        try:
                            info = p.memory_info(); cpu = p.cpu_times()
                            self.cpu_times[(p.pid, p.create_time())] = cpu.user + cpu.system
                            rss += info.rss; commit += getattr(info, 'private', info.vms)
                            faults += getattr(info, 'num_page_faults', 0)
                            children.append(dict(pid=p.pid, rss=info.rss, name=p.name()))
                        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
                    now = perf_counter(); total = sum(self.cpu_times.values())
                    cpu_percent = max(0., (total - self.last_cpu) / max(.001, now-last) * 100) if self.records else 0.
                    self.last_cpu, last = total, now
                    row = dict(elapsed=now-self.started, phase=self.state.get('phase'),
                        document=self.state.get('member'), stage=self.state.get('stage'),
                        process_tree_cpu_percent=cpu_percent, machine_cpu_percent=psutil.cpu_percent(None),
                        rss_bytes=rss, private_commit_bytes=commit, job_peak_commit_bytes=self.budget.peak(),
                        system_available_ram_bytes=psutil.virtual_memory().available,
                        page_faults_total_including_soft=faults, hard_paging_rate='UNAVAILABLE',
                        cpu_actual_clock='UNAVAILABLE', cpu_temperature='UNAVAILABLE',
                        active_ocr=self.state.get('active_ocr'),active_model=self.state.get('active_model'),
                        gpu_device_wide=self.gpu, children=children)
                    stream.write(json.dumps(row) + '\n'); stream.flush(); self.records.append(row)
                except Exception as error: self.errors.append(type(error).__name__)
                self.stop.wait(1.)

    def finish(self):
        self.stop.set(); self.thread.join(5)
        if self.nvprocess:
            self.nvprocess.terminate(); self.nvprocess.wait(timeout=10); self.nvprocess.stdout.close()
        return self.records
