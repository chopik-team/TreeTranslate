"""Build-only FreeDict importer. Network requires --allow-network; runtime reads SQLite.

Input archives are version pinned and checked against official SHA512 sidecars.
No tar paths are extracted. The derived dictionary retains CC BY-SA 3.0.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile
import unicodedata
from urllib.request import urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2025.11.23"
PAIRS = {"eng-rus": ("en", "ru"), "rus-eng": ("ru", "en")}
NS = {"t": "http://www.tei-c.org/ns/1.0"}


def key(text):
    return unicodedata.normalize("NFC", text.replace("\u0301", "")).casefold().strip()


def texts(element, xpath):
    return list(dict.fromkeys("".join(node.itertext()).strip() for node in element.findall(xpath, NS)))


def import_tei(connection, data, source, target):
    tree = ET.fromstring(data)  # stdlib does not fetch external DTDs/entities
    count = 0
    for entry in tree.findall(".//t:entry", NS):
        words = texts(entry, "t:form/t:orth")
        senses = []
        for sense in entry.findall("t:sense", NS):
            translations = texts(sense, "t:cit[@type='trans']/t:quote")
            if translations:
                senses.append({"translations": translations, "definitions": texts(sense, ".//t:def")})
        payload = dict(headword=words[0] if words else "", pronunciation=texts(entry, "t:form/t:pron"),
                       pos=texts(entry, "t:gramGrp/t:pos"), senses=senses,
                       attribution="FreeDict / WikDict / Wiktionary · CC BY-SA 3.0")
        for word in words:
            connection.execute("INSERT INTO entries VALUES (?, ?, ?, ?)",
                               (source, target, key(word), json.dumps(payload, ensure_ascii=False)))
            count += 1
    return count, ET.tostring(tree.find("t:teiHeader", NS), encoding="unicode")


def prepare(source_dir, output, allow_network=False):
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    source_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    # Stage the complete database; interruption cannot leave a valid-looking partial DB.
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        staged = Path(temporary) / "lexicon.sqlite3"
        with closing(sqlite3.connect(staged)) as connection, connection:
            connection.execute("CREATE TABLE entries (source TEXT, target TEXT, key TEXT, payload TEXT)")
            for pair, (source, target) in PAIRS.items():
                name = f"freedict-{pair}-{VERSION}.src.tar.xz"
                path = source_dir / name
                sidecar = source_dir / (name + ".sha512")
                url = f"https://download.freedict.org/dictionaries/{pair}/{VERSION}/{name}"
                if not path.exists() or not sidecar.exists():
                    if not allow_network:
                        raise FileNotFoundError(f"Provide {path} and its .sha512 sidecar, or use --allow-network")
                    with urlopen(url, timeout=60) as response:
                        path.write_bytes(response.read(64 * 1024 * 1024 + 1))
                    with urlopen(url + ".sha512", timeout=30) as response:
                        sidecar.write_bytes(response.read(4096))
                digest = hashlib.sha512(path.read_bytes()).hexdigest()
                if digest != sidecar.read_text().split()[0]:
                    raise ValueError("FreeDict SHA512 mismatch")
                with tarfile.open(path) as archive:
                    member = next(item for item in archive.getmembers() if item.name.endswith(f"/{pair}.tei"))
                    if not member.isfile() or member.size > 128 * 1024 * 1024:
                        raise ValueError("Invalid TEI archive member")
                    count, header = import_tei(connection, archive.extractfile(member).read(), source, target)
                (output.parent / f"{pair}-attribution.xml").write_text(header, encoding="utf-8")
                records.append(dict(pair=pair, entries=count, version=VERSION, url=url, sha512=digest))
            connection.execute("CREATE INDEX lookup ON entries (source, target, key)")
            connection.execute("PRAGMA user_version=1")
        staged.replace(output)
    manifest = dict(schema=1, sources=records, license="CC-BY-SA-3.0",
                    changes="TEI entries converted to indexed SQLite; stress-insensitive lookup keys added.",
                    sha256=hashlib.sha256(output.read_bytes()).hexdigest(), bytes=output.stat().st_size)
    (output.parent / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "build" / "lexicon-sources")
    parser.add_argument("--output", type=Path, default=ROOT / "vendor" / "lexicon" / "lexicon.sqlite3")
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_dir, args.output, args.allow_network), ensure_ascii=False, indent=2))
