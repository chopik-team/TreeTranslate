"""Manual CPU thread calibration on fixed public technical examples."""
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.evaluate_decoding import EvaluationDevices
from app.engine.factory import create_translation_engine
from app.engine.types import DevicePreference, TranslationRequest


def main():
    engine = create_translation_engine()
    devices = EvaluationDevices()
    devices.beam = 4
    engine.devices = devices
    cases = json.loads((ROOT / "tools" / "quality_corpus.json").read_text(encoding="utf-8"))["cases"]
    rows = []
    try:
        for backend in ("argos", "m2m100"):
            for threads in (2, 4, 8, 16):
                devices.threads = threads
                for case in (c for c in cases if c["id"] in {"en-game", "zh-technical"}):
                    request = TranslationRequest(case["text"], case["source"], case["target"], DevicePreference.CPU)
                    engine.translate(request, backend_only=backend)
                    samples = [engine.translate(request, backend_only=backend).duration_ms for _ in range(5)]
                    rows.append(dict(backend=backend, threads=threads, beam=4, case=case["id"], samples_ms=samples,
                                     median_ms=statistics.median(samples)))
                    print(backend, threads, case["id"], round(statistics.median(samples), 1), flush=True)
    finally:
        engine.shutdown()
    (ROOT / "docs" / "benchmarks" / "aw04-cpu-threads.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
