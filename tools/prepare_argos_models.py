"""Build-only Argos package preparation; downloads require --allow-network."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.model_artifacts import record_model

INDEX = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"


def prepare(package_path: Path, root: Path, source: str) -> None:
    argos_root = root / "argos"
    argos_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=argos_root, prefix=".prepare-") as temporary:
        stage = Path(temporary).resolve()
        with zipfile.ZipFile(package_path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 3_000_000_000:
                raise ValueError("Package too large")
            for item in archive.infolist():
                target = (stage / item.filename).resolve()
                if not target.is_relative_to(stage) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe archive path")
            archive.extractall(stage)
        metadata_files = list(stage.glob("*/metadata.json"))
        if len(metadata_files) != 1:
            raise ValueError("Expected one Argos package root")
        folder = metadata_files[0].parent
        os.environ["ARGOS_PACKAGES_DIR"] = str(argos_root)
        os.environ["ARGOS_DEBUG"] = "0"
        from argostranslate.package import Package
        pkg = Package(folder)
        if pkg.type != "translate" or not (folder / "model" / "model.bin").is_file():
            raise ValueError("Not a local translation package")
        if not hasattr(pkg, "tokenizer"):
            raise ValueError("Tokenizer missing")
        model_id = f"argos-{pkg.from_code}-{pkg.to_code}"
        if not all(part.isalnum() for part in [pkg.from_code, pkg.to_code]):
            raise ValueError("Invalid language codes")
        output = argos_root / model_id
        if output.exists():
            raise ValueError(f"Output already exists: {output}")
        licenses = [p for p in folder.rglob("*") if p.is_file() and p.name.lower().startswith(("license", "licence", "copying"))]
        license_text = "UNKNOWN: package has no license file; review upstream before distribution"
        if licenses:
            # Record the exact artifact, not a guessed SPDX license for the weights.
            license_text = "See bundled " + ", ".join(p.relative_to(folder).as_posix() for p in licenses)
        elif (folder / "README.md").is_file() and "original OPUS model" in (folder / "README.md").read_text(encoding="utf-8"):
            card = (folder / "README.md").read_text(encoding="utf-8")
            if "licensed CC-BY 4.0" in card:
                license_text = "CC-BY-4.0 for original OPUS model, per bundled README; package-wide terms not separately stated"
        if not folder.resolve().is_relative_to(stage) or not output.resolve().is_relative_to(argos_root.resolve()):
            raise ValueError("Move must stay inside the model preparation directory")
        shutil.move(str(folder), str(output))
        row = record_model(root, output, model_id=model_id, backend="argos", version=str(pkg.package_version),
                           source=source, languages=[pkg.from_code, pkg.to_code], pairs=[[pkg.from_code, pkg.to_code]],
                           quantization="upstream", license_text=license_text)
        print(json.dumps({"id": row["id"], "size": row["size"], "license": row["license"]}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", type=Path, nargs="*")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--pairs", nargs="*", default=[])
    parser.add_argument("--models-root", type=Path, default=Path("vendor/models"))
    parser.add_argument("--source-cache", type=Path, default=Path("build/model-sources/argos"))
    args = parser.parse_args()
    if args.pairs and not args.allow_network:
        parser.error("--pairs requires --allow-network; use local .argosmodel files otherwise")
    root = args.models_root.resolve()
    sources = [(p.resolve(), str(p.resolve())) for p in args.packages]
    if args.pairs:
        with urllib.request.urlopen(INDEX, timeout=60) as response:
            index = json.load(response)
        args.source_cache.mkdir(parents=True, exist_ok=True)
        for pair in args.pairs:
            source, target = pair.split("-")
            matches = [p for p in index if (p.get("from_code"), p.get("to_code")) == (source, target)]
            if not matches:
                parser.error(f"No official package for {pair}")
            from packaging.version import Version
            package = max(matches, key=lambda p: Version(p["package_version"]))
            url = next((url for url in package["links"] if url.startswith("https://argos-net.com/")), None)
            if url is None:
                parser.error("Upstream package has no trusted HTTPS artifact URL")
            path = args.source_cache / url.rsplit("/", 1)[-1]
            if not path.exists():
                temp = path.with_suffix(".partial")
                request = urllib.request.Request(url, headers={"User-Agent": "ArgosTranslate"})
                with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as out:
                    shutil.copyfileobj(response, out)
                os.replace(temp, path)
            sources.append((path.resolve(), url))
    if not sources:
        parser.error("Provide local packages or --allow-network --pairs en-ru ru-en")
    for path, source in sources:
        prepare(path, root, source)


if __name__ == "__main__":
    main()
