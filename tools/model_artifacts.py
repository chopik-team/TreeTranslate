"""Build-only manifest/checksum helpers. Never imported by the application."""
import hashlib
import json
import os
from pathlib import Path
import shutil


def record_model(root: Path, folder: Path, *, model_id: str, backend: str, version: str,
                 source: str, languages: list[str], pairs: list[list[str]],
                 quantization: str, license_text: str) -> dict:
    files = []
    for file in sorted(folder.rglob("*")):
        if file.is_file():
            with file.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files.append(dict(path=file.relative_to(folder).as_posix(), size=file.stat().st_size, sha256=digest))
    row = dict(id=model_id, backend=backend, path=folder.relative_to(root).as_posix(), version=version,
               source=source, languages=languages, pairs=pairs, format="ctranslate2",
               quantization=quantization, license=license_text, size=sum(f["size"] for f in files), files=files)
    manifest = root / "models_manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else dict(schema_version=1, models=[])
    data["models"] = [item for item in data["models"] if item["id"] != model_id] + [row]
    temp = manifest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, manifest)
    # Keep provenance/licenses reviewable in Git while large model trees stay ignored.
    metadata = root.parent / "model-metadata" / model_id
    metadata.mkdir(parents=True, exist_ok=True)
    for file in folder.iterdir():
        if file.is_file() and (file.name.lower().startswith(("readme", "license", "licence", "copying", "upstream")) or file.name == "metadata.json"):
            shutil.copyfile(file, metadata / file.name)
    return row
