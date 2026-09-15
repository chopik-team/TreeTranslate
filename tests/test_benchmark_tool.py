import json
from pathlib import Path
import subprocess
import sys


def test_missing_models_are_errors_not_fabricated_benchmark_measurements(tmp_path):
    output = tmp_path / "benchmark.json"
    run = subprocess.run([sys.executable, "tools/benchmark_translation.py", "--models-root", str(tmp_path / "missing"),
                          "--devices", "cpu", "--backends", "m2m100", "--cases", "zh-ru-short",
                          "--repeats", "1", "--warmup", "0", "--output", str(output)],
                         capture_output=True, timeout=30)
    assert run.returncode == 1
    row, = json.loads(output.read_text(encoding="utf-8"))["results"]
    assert row["errors"][0]["error_type"] == "ModelMissingError"
    assert "warm_median_ms" not in row
    assert "translated_text" not in row
