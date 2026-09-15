"""Manual offline benchmark. Fresh subprocess per case/backend/device/profile.

Cold latency includes local discovery/import/model load; warm latency includes
router/tokenization/inference. No user text or model outputs enter the report.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from threading import Event, Thread
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def local_command(args):
    try:
        return subprocess.check_output(args, text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def gpu_used_mb():
    value = local_command(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
    try:
        return int(value.splitlines()[0]) if value else None
    except ValueError:
        return None


class MemorySampler:
    def __init__(self):
        try:
            import psutil
            self.process = psutil.Process()
        except ImportError:
            self.process = None
        self.peak = self.rss()
        self.stop = Event()
        self.thread = Thread(target=self.sample, daemon=True)

    def rss(self):
        return self.process.memory_info().rss / 1024**2 if self.process else None

    def sample(self):
        while not self.stop.wait(0.02):
            value = self.rss()
            if value is not None:
                self.peak = max(self.peak or 0, value)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join()


def measure(args, case):
    from app.engine.factory import create_translation_engine
    from app.engine.types import DevicePreference, PerformanceProfile, TranslationRequest
    engine = create_translation_engine(args.models_root)
    request = TranslationRequest(case["text"], case["source"], case["target"],
                                 DevicePreference(args.devices[0]), PerformanceProfile(args.profiles[0]))
    chosen = args.backends[0]
    memory = MemorySampler()
    record = dict(case=case["id"], source=case["source"], target=case["target"],
                  requested_backend=chosen, requested_device=args.devices[0], profile=args.profiles[0],
                  chars=len(case["text"]), words=len(case["text"].split()) if case["source"] not in {"zh", "ja"} else None,
                  word_count_method="whitespace; null for zh/ja",
                  rss_before_mb=memory.rss(), gpu_total_before_mb=gpu_used_mb(), errors=[])
    record["profile_settings"] = asdict(engine.policy.profile(request.performance_profile, request.cpu_threads))
    memory.start()
    samples = []
    try:
        for iteration in range(1 + args.warmup + args.repeats):
            start = perf_counter()
            try:
                result = engine.translate(request, backend_only=None if chosen == "router" else chosen)
            except Exception as error:
                record["errors"].append({"iteration": iteration, "error_type": type(error).__name__,
                                         "elapsed_ms": (perf_counter() - start) * 1000})
                break
            elapsed = (perf_counter() - start) * 1000
            if iteration == 0:
                record["cold_ms"] = elapsed
            if iteration > args.warmup:
                samples.append(elapsed)
            record.update(backend=result.backend, device=result.device, compute_type=result.compute_type,
                          model_ids=list(result.model_ids), route_reason=result.route_reason, fallback_used=result.fallback_used)
        if samples:
            median = statistics.median(samples)
            record.update(warm_samples_ms=samples, warm_median_ms=median,
                          warm_p95_ms=sorted(samples)[max(0, math.ceil(0.95 * len(samples)) - 1)],
                          chars_per_sec=record["chars"] * 1000 / median,
                          words_per_sec=record["words"] * 1000 / median if record["words"] else None)
        record["rss_loaded_mb"] = memory.rss()
        record["gpu_total_loaded_mb"] = gpu_used_mb()
        record["attempt_metrics"] = [asdict(metric) for metric in engine.metrics]
    finally:
        engine.shutdown()
        memory.close()
    record["rss_sampled_peak_mb"] = memory.peak
    record["rss_after_shutdown_mb"] = memory.rss()
    record["gpu_total_after_shutdown_mb"] = gpu_used_mb()
    return record


def summary_markdown(report):
    lines = ["# TreeTranslate AW 0.4 — измеренная производительность", "",
             f"Дата UTC: {report['created_at']}", "",
             "Скорость на синтетическом корпусе; оценок качества нет. Все задержки — мс.",
             "Cold: первый запрос в новом процессе; Warm: медиана повторных запросов без кэша перевода.",
             "RAM: RSS процесса, peak sampled каждые 20 мс. VRAM: общая занятая память GPU в контрольных точках; это не пик VRAM процесса.", "",
             "| Профиль | Запрошено | Устройство | Корпус | Реальный маршрут | Cold | Warm | Симв/с | Ошибки |",
             "|---|---|---|---|---|---:|---:|---:|---|"]
    for row in report["results"]:
        def number(key):
            return f"{row[key]:.1f}" if key in row else "—"
        route = row.get("backend", "—") + (" pivot" if "pivot" in row.get("route_reason", "") else "")
        lines.append(f"| {row['profile']} | {row['requested_backend']} | {row.get('device', row['requested_device'])} | {row['case']} | {route} | {number('cold_ms')} | {number('warm_median_ms')} | {number('chars_per_sec')} | {', '.join(e['error_type'] for e in row['errors']) or '0'} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-root", type=Path, default=Path("vendor/models"))
    parser.add_argument("--corpus", type=Path, default=Path(__file__).with_name("benchmark_corpus.json"))
    parser.add_argument("--backends", nargs="+", choices=["argos", "m2m100", "router"], default=["argos", "m2m100", "router"])
    parser.add_argument("--devices", nargs="+", choices=["cpu", "gpu", "auto"], default=["cpu", "gpu"])
    parser.add_argument("--profiles", nargs="+", choices=["economy", "fast", "balanced", "turbo", "maximum", "automatic"], default=["balanced"])
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("benchmark-results/translation.json"))
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 1 or args.warmup < 0:
        parser.error("repeats >= 1 and warmup >= 0 required")
    cases = json.loads(args.corpus.read_text(encoding="utf-8"))["cases"]
    if args.cases:
        if set(args.cases) - {case["id"] for case in cases}:
            parser.error("Unknown corpus case id")
        cases = [case for case in cases if case["id"] in args.cases]
    if args.worker:
        print(json.dumps(measure(args, cases[0]), ensure_ascii=True))
        return
    versions = {}
    for name in ["ctranslate2", "argostranslate", "sentencepiece", "numpy", "langid", "nvidia-cublas-cu12"]:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    cpu = local_command(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"]) if os.name == "nt" else platform.processor()
    report = dict(schema_version=1, created_at=datetime.now(timezone.utc).isoformat(),
                  hardware=dict(cpu=cpu, logical_cpus=os.cpu_count(), gpu=local_command([
                      "nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"])),
                  python=sys.version, platform=platform.platform(), versions=versions,
                  corpus_sha256=hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
                  profiles_sha256=hashlib.sha256((Path(__file__).resolve().parents[1] / "app/config/engine_profiles.json").read_bytes()).hexdigest(),
                  repeats=args.repeats, warmup=args.warmup, results=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    total = len(args.backends) * len(args.devices) * len(args.profiles) * len(cases)
    for profile in args.profiles:
        for backend in args.backends:
            for device in args.devices:
                for case in cases:
                    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--backends", backend,
                               "--devices", device, "--profiles", profile, "--cases", case["id"],
                               "--models-root", str(args.models_root.resolve()), "--corpus", str(args.corpus.resolve()),
                               "--repeats", str(args.repeats), "--warmup", str(args.warmup)]
                    try:
                        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=300,
                                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        if run.returncode:
                            raise RuntimeError("worker failed")
                        row = json.loads(run.stdout)
                    except (subprocess.TimeoutExpired, RuntimeError, ValueError):
                        row = dict(case=case["id"], requested_backend=backend, requested_device=device, profile=profile,
                                   errors=[dict(error_type="BenchmarkWorkerError")])
                    report["results"].append(row)
                    # Checkpoint after each subprocess, so interrupted long runs keep measurements.
                    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    print(f"{len(report['results'])}/{total} {profile} {backend} {device} {case['id']} errors={len(row['errors'])}", flush=True)
    args.output.with_suffix(".md").write_text(summary_markdown(report), encoding="utf-8")
    fields = ["case", "profile", "requested_backend", "requested_device", "backend", "device", "compute_type", "cold_ms",
              "warm_median_ms", "warm_p95_ms", "chars_per_sec", "words_per_sec", "rss_sampled_peak_mb", "gpu_total_loaded_mb"]
    with args.output.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["results"])
    print(f"Saved {args.output}")
    if any(row["errors"] for row in report["results"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
