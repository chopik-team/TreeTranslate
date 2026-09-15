"""Manual offline SHA256 verification; never part of GUI startup."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine.runtime.model_manager import ModelManager
from app.config.paths import MODELS_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-root", type=Path, default=MODELS_DIR)
    args = parser.parse_args()
    manager = ModelManager(args.models_root)
    if not manager.records:
        parser.error("No prepared models in manifest")
    for record in manager.records:
        manager.validate(record, full=True)
        print(f"OK {record.id} {record.size} bytes")


if __name__ == "__main__":
    main()
