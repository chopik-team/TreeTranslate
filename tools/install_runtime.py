"""Explicit developer/install step; app code never imports this module."""
import argparse
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, help="Offline wheel directory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = ["--no-index", "--find-links", str(args.wheelhouse.resolve())] if args.wheelhouse else []
    for filename, extra in [("requirements-runtime-lock.txt", []), ("requirements-argos.txt", ["--no-deps"])]:
        subprocess.run([sys.executable, "-m", "pip", "install", *source, *extra,
                        "-r", str(root / filename)], check=True)


if __name__ == "__main__":
    main()
