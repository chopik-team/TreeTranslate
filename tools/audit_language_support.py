"""Build the AW0.7.6 offline language support matrix from real local inference."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.paths import ASSETS_DIR, MODELS_DIR
from app.engine.backends.argos_backend import ArgosBackend
from app.engine.backends.m2m100_backend import M2M100Backend
from app.engine.languages import LanguageResolver, language_code
from app.engine.errors import TranslationError
from app.engine.router.translation_router import TranslationRouter
from app.engine.runtime.model_manager import ModelManager
from app.engine.types import DevicePreference, PerformanceProfile, TranslationRequest
from app.gui.widgets.language_selector import LanguageSelector


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "This is a short offline translation test."
CONTROL_TOKEN = re.compile(r"(?:__[^\s]+__|<unk>|</?s>|<pad>|\ufffd|[\x00-\x08\x0b\x0c\x0e-\x1f])")
AUTO_SAMPLES = {
    "ru": "Это короткая проверка локального перевода на русском языке.",
    "en": "This is a short offline translation test in English.",
    "zh": "这是一个简短的中文离线翻译测试。",
    "de": "Dies ist ein kurzer deutscher Übersetzungstest.",
    "es": "Esta es una breve prueba de traducción en español.",
    "fr": "Ceci est un court test de traduction en français.",
    "ja": "これは日本語の短いオフライン翻訳テストです。",
}


def valid_output(text: str) -> bool:
    return bool(text.strip()) and CONTROL_TOKEN.search(text) is None


def request(text: str, source: str, target: str) -> TranslationRequest:
    return TranslationRequest(
        text, source, target, DevicePreference.GPU, PerformanceProfile.FAST, cpu_threads=8,
    )


def smoke_translate(router, text: str, source: str, target: str, *, backend_only=None):
    try:
        result = router.translate(request(text, source, target), backend_only=backend_only)
        return result, None
    except TranslationError as error:
        return None, type(error).__name__


def build_matrix() -> dict:
    manager = ModelManager(MODELS_DIR)
    m2m_record = next(record for record in manager.records if record.id == "m2m100-418m-int8")
    model_languages = tuple(sorted(m2m_record.languages))
    labels_by_code: dict[str, list[str]] = {}
    for label in LanguageSelector.LANGUAGES:
        labels_by_code.setdefault(language_code(label), []).append(label)
    release_codes = tuple(labels_by_code)

    router = TranslationRouter({"argos": ArgosBackend(manager), "m2m100": M2M100Backend(manager)})
    resolver = LanguageResolver()
    generated = {"en": FIXTURE}
    rows = []
    try:
        for code in model_languages:
            print(f"audit language={code}", flush=True)
            if code == "en":
                outbound = FIXTURE
                outbound_backend = "passthrough"
                outbound_ms = 0.0
            else:
                result, outbound_error = smoke_translate(
                    router, FIXTURE, "en", code, backend_only="m2m100"
                )
                if result is None:
                    outbound, outbound_backend, outbound_ms = "", "m2m100", 0.0
                else:
                    outbound, outbound_backend, outbound_ms = result.translated_text, result.backend, result.duration_ms
            if code == "en":
                outbound_error = None
            generated[code] = outbound
            outbound_ok = valid_output(outbound)
            if code == "en":
                inbound = FIXTURE
                inbound_backend = "passthrough"
                inbound_ms = 0.0
            elif outbound_ok:
                result, inbound_error = smoke_translate(
                    router, outbound, code, "en", backend_only="m2m100"
                )
                if result is None:
                    inbound, inbound_backend, inbound_ms = "", "m2m100", 0.0
                else:
                    inbound, inbound_backend, inbound_ms = result.translated_text, result.backend, result.duration_ms
            else:
                inbound, inbound_backend, inbound_ms = "", "m2m100", 0.0
                inbound_error = "outbound_failed"
            if code == "en":
                inbound_error = None
            inbound_ok = valid_output(inbound)
            ui_available = code in release_codes
            status = "RELEASE_READY" if ui_available and outbound_ok and inbound_ok else (
                "EXPERIMENTAL" if outbound_ok and inbound_ok else "BROKEN"
            )
            detected = None
            if code in AUTO_SAMPLES:
                detected = resolver.resolve(AUTO_SAMPLES[code], "auto", "ru")[0]
            rows.append({
                "code": code,
                "ui_labels": labels_by_code.get(code, []),
                "ui_available": ui_available,
                "status": status,
                "backend": "m2m100",
                "route": "direct",
                "smoke": {
                    "en_to_language": {"ok": outbound_ok, "backend": outbound_backend,
                                       "duration_ms": round(outbound_ms, 2), "error": outbound_error},
                    "language_to_en": {"ok": inbound_ok, "backend": inbound_backend,
                                       "duration_ms": round(inbound_ms, 2), "error": inbound_error},
                },
                "auto_detect": {"tested": detected is not None, "detected": detected,
                                "ok": detected == code if detected is not None else None},
                "documents": {"docx": ui_available, "native_pdf": ui_available,
                              "ocr": code in {"en", "ru", "zh"}},
                "technical_glossary": "STRONG" if code in {"ru", "zh"} else "NONE",
                "dictionary": "YES" if code in {"en", "ru"} else "NO",
                "usage_examples": "YES" if code in {"en", "ru"} else "NO",
            })

        directions = []
        capabilities, _ = router._capabilities()
        for source in release_codes:
            for target in release_codes:
                if source == target:
                    continue
                decision = router.decide(request(generated[source], source, target), capabilities)
                translated, error = smoke_translate(router, generated[source], source, target)
                directions.append({
                    "source": source,
                    "target": target,
                    "status": "RELEASE_READY" if translated and valid_output(translated.translated_text) else "BROKEN",
                    "backend": translated.backend if translated else None,
                    "expected_backend": decision.backend,
                    "route": decision.kind.value,
                    "fallback": translated.fallback_used if translated else None,
                    "device": translated.device if translated else None,
                    "duration_ms": round(translated.duration_ms, 2) if translated else 0.0,
                    "output_ok": bool(translated and valid_output(translated.translated_text)),
                    "error": error,
                })
    finally:
        resolver.shutdown()
        router.shutdown()

    translation_bytes = sum(record.size for record in manager.records)
    lexical_bytes = (ROOT / "vendor/lexicon/lexicon.sqlite3").stat().st_size
    knowledge_bytes = sum(path.stat().st_size for path in (ASSETS_DIR / "knowledge").glob("*.db"))
    usage_bytes = (ASSETS_DIR / "language/usage.json").stat().st_size
    statuses = ("RELEASE_READY", "EXPERIMENTAL", "BROKEN", "UNSUPPORTED")
    raw_counts = Counter(row["status"] for row in rows)
    raw_direction_counts = Counter(row["status"] for row in directions)
    counts = {status: raw_counts[status] for status in statuses}
    direction_counts = {status: raw_direction_counts[status] for status in statuses}
    return {
        "schema": 1,
        "audit_date": date.today().isoformat(),
        "scope": "100 M2M100 model codes; W1.0 release-facing UI is limited to seven unique codes",
        "release_language_codes": list(release_codes),
        "release_ui_labels": list(LanguageSelector.LANGUAGES),
        "model_language_count": len(model_languages),
        "language_status_counts": counts,
        "release_direction_status_counts": direction_counts,
        "runtime_size_before_bytes": translation_bytes + lexical_bytes + knowledge_bytes + usage_bytes,
        "runtime_size_after_bytes": translation_bytes + lexical_bytes + knowledge_bytes + usage_bytes,
        "languages": rows,
        "directions": directions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/qa/aw076/language-matrix.json")
    args = parser.parse_args()
    matrix = build_matrix()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: matrix[key] for key in (
        "model_language_count", "language_status_counts", "release_direction_status_counts",
        "runtime_size_before_bytes", "runtime_size_after_bytes",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
