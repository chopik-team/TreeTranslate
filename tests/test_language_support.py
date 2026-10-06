import json
from pathlib import Path
import socket

import pytest
from app.engine.languages import RELEASE_LANGUAGE_CODES, RELEASE_LANGUAGE_LABELS
from app.config.paths import MODELS_DIR
from app.engine.factory import create_translation_engine
from app.engine.runtime.model_manager import ModelManager
from app.engine.types import DevicePreference, PerformanceProfile, TranslationRequest
from app.gui.widgets.language_selector import LanguageSelector
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from app.services.settings_service import SettingsService
from app.services.translation_preferences import TranslationPreferences
from tools.audit_language_support import AUTO_SAMPLES, valid_output


MATRIX = Path("docs/qa/aw076/language-matrix.json")


def matrix():
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_release_language_matrix_matches_ui_and_model_manifest():
    data = matrix()
    assert data["release_ui_labels"] == list(RELEASE_LANGUAGE_LABELS)
    assert set(data["release_language_codes"]) == RELEASE_LANGUAGE_CODES
    model = next(record for record in ModelManager(MODELS_DIR).records if record.id == "m2m100-418m-int8")
    assert {row["code"] for row in data["languages"]} == set(model.languages)
    assert data["model_language_count"] == len(model.languages) == 100


def test_every_release_direction_passed_real_inference():
    data = matrix()
    directions = data["directions"]
    assert len(directions) == len(RELEASE_LANGUAGE_CODES) * (len(RELEASE_LANGUAGE_CODES) - 1) == 42
    assert all(row["status"] == "RELEASE_READY" and row["output_ok"] for row in directions)
    assert all(row["backend"] == row["expected_backend"] for row in directions)
    assert not any(row["fallback"] for row in directions)


def test_release_languages_auto_detect_and_capability_disclosure():
    release = {row["code"]: row for row in matrix()["languages"] if row["ui_available"]}
    assert set(release) == RELEASE_LANGUAGE_CODES == set(AUTO_SAMPLES)
    assert all(row["status"] == "RELEASE_READY" for row in release.values())
    assert all(row["auto_detect"]["ok"] for row in release.values())
    assert {code for code, row in release.items() if row["dictionary"] == "YES"} == {"en", "ru"}
    assert {code for code, row in release.items() if row["documents"]["ocr"]} == {"en", "ru", "zh"}


def test_matrix_statuses_and_runtime_size_are_complete():
    data = matrix()
    assert set(data["language_status_counts"]) == {
        "RELEASE_READY", "EXPERIMENTAL", "BROKEN", "UNSUPPORTED",
    }
    assert sum(data["language_status_counts"].values()) == 100
    assert data["runtime_size_before_bytes"] == data["runtime_size_after_bytes"]
    assert data["release_direction_status_counts"]["BROKEN"] == 0


def test_release_target_selector_never_exposes_auto():
    app = QApplication.instance() or QApplication([])
    selector = LanguageSelector()
    assert selector.source_combo.findText(selector.AUTOMATIC) >= 0
    assert selector.target_combo.findText(selector.AUTOMATIC) == -1
    selector.close()


def test_legacy_automatic_target_setting_is_migrated(tmp_path):
    raw = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    raw.setValue("language/source", "Русский")
    raw.setValue("language/target", "Определить автоматически")
    settings = SettingsService(raw)
    preferences = TranslationPreferences(settings)
    assert preferences.target_language == "Английский"
    assert raw.value("language/target") == "Английский"
    preferences.set_languages("Русский", "Определить автоматически")
    assert preferences.target_language == "Английский"


def test_smoke_output_rejects_model_and_control_tokens():
    assert valid_output("Локальный перевод готов.")
    assert not valid_output("")
    assert not valid_output("__ru__ translated")
    assert not valid_output("broken\ufffdtext")


@pytest.mark.integration
def test_release_languages_cpu_and_auto_real_offline_smoke(monkeypatch):
    attempts = []

    def forbidden(*_args, **_kwargs):
        attempts.append(True)
        raise AssertionError("Runtime attempted network access")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    engine = create_translation_engine()
    try:
        for device in (DevicePreference.CPU, DevicePreference.AUTO):
            for target in ("ru", "zh", "de", "ja", "es", "fr"):
                result = engine.translate(TranslationRequest(
                    "This is a short offline translation test.", "en", target,
                    device, PerformanceProfile.FAST,
                ))
                assert valid_output(result.translated_text), (device, target)
                assert result.source_language == "en" and result.target_language == target
                assert result.backend in {"argos", "m2m100"}
        for target in ("de", "ja", "es", "fr"):
            result = engine.translate(TranslationRequest(
                "This is a short offline translation test.", "en", target,
                DevicePreference.CPU, PerformanceProfile.ECONOMY,
            ))
            assert result.backend == "m2m100" and valid_output(result.translated_text)
        assert not attempts
    finally:
        engine.shutdown()
