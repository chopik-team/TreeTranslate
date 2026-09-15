"""Development-only evaluation of the fixed, original quality_corpus.json.

Unlike the private runtime metrics, this report retains synthetic translations
for manual review. Concept checks are diagnostics, not BLEU/COMET or human ratings.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.factory import create_translation_engine
from app.engine.runtime.device_manager import DeviceManager
from app.engine.types import DevicePreference, PerformanceProfile, TranslationRequest


class EvaluationDevices(DeviceManager):
    beam = 4
    threads = 4

    def options(self, device, policy):
        return tuple(replace(option, beam_size=self.beam, threads=self.threads)
                     for option in super().options(device, policy))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=["cpu", "gpu"], default="gpu")
    parser.add_argument("--beams", nargs="+", type=int, default=[1, 2, 4, 5, 8])
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus = json.loads((ROOT / "tools" / "quality_corpus.json").read_text(encoding="utf-8"))
    engine = create_translation_engine()
    devices = EvaluationDevices()
    devices.threads = args.threads
    engine.devices = devices
    rows = []
    try:
        for backend in ("argos", "m2m100"):
            for beam in args.beams:
                devices.beam = beam
                # Exclude native startup from each measured setting.
                engine.translate(TranslationRequest("The game is ready.", "en", "ru", DevicePreference(args.device)), backend_only=backend)
                for case in corpus["cases"]:
                    request = TranslationRequest(case["text"], case["source"], case["target"], DevicePreference(args.device), PerformanceProfile.BALANCED)
                    result = engine.translate(request, backend_only=backend)
                    output = result.translated_text
                    checks = [any(value.casefold() in output.casefold() for value in concept) for concept in case["concepts"]]
                    rows.append(dict(case=case["id"], source=case["text"], backend=backend, beam=beam, threads=args.threads,
                                     device=result.device, compute_type=result.compute_type, output=output,
                                     checks=checks, latency_ms=result.duration_ms))
                subset = rows[-len(corpus["cases"]):]
                print(backend, beam, "concepts", sum(sum(row["checks"]) for row in subset),
                      "median_ms", round(statistics.median(row["latency_ms"] for row in subset), 1), flush=True)
    finally:
        engine.shutdown()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(), disclaimer=corpus["description"], rows=rows)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
