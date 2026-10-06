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

try:
    from tools.lexical_expansion import (
        add_source, create_expansion_schema, expanded_statistics, import_openrussian,
        import_tatoeba, import_wordnet, sha256,
    )
except ModuleNotFoundError:  # direct ``python tools/prepare_lexicon.py`` invocation
    from lexical_expansion import (
        add_source, create_expansion_schema, expanded_statistics, import_openrussian,
        import_tatoeba, import_wordnet, sha256,
    )

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


EXPANSION_FILES = {
    "wordnet.zip": "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip",
    "openrussian-nouns.csv": "https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/nouns.csv",
    "openrussian-verbs.csv": "https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/verbs.csv",
    "openrussian-adjectives.csv": "https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/adjectives.csv",
    "openrussian-others.csv": "https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/others.csv",
    "openrussian-LICENSE.txt": "https://raw.githubusercontent.com/Badestrand/russian-dictionary/master/LICENSE",
    "tatoeba-eng.tsv.bz2": "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences_detailed.tsv.bz2",
    "tatoeba-rus.tsv.bz2": "https://downloads.tatoeba.org/exports/per_language/rus/rus_sentences_detailed.tsv.bz2",
}
EXPANSION_ACQUISITION_DATE = "2026-09-27"


def expansion_source_metadata(name):
    if name == "wordnet.zip":
        return {
            "revision": "nltk-data 550b6625bcef1f2abff2ff770a5a0d272c9c6b2a",
            "license": "WordNet-3.0",
            "attribution": "Princeton University WordNet 3.0",
        }
    if name.startswith("openrussian-"):
        return {
            "revision": "50e210c4803237779cb562bc1abcea529066031c",
            "license": "CC-BY-SA-4.0",
            "attribution": "OpenRussian.org contributors",
        }
    return {
        "revision": "2026-09-26",
        "license": "CC-BY-2.0-FR",
        "attribution": "Tatoeba contributors; sentence ID and contributor retained",
    }


def acquire_expansion_sources(directory: Path, allow_network=False):
    directory.mkdir(parents=True, exist_ok=True)
    for name, url in EXPANSION_FILES.items():
        path = directory / name
        if path.exists():
            continue
        if not allow_network:
            raise FileNotFoundError(f"Provide {path}, or use --allow-network")
        with urlopen(url, timeout=120) as response, path.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)


def prepare(source_dir, output, allow_network=False, expansion_source_dir=None):
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
            expansion = None
            if expansion_source_dir is not None:
                expansion_source_dir = Path(expansion_source_dir)
                acquire_expansion_sources(expansion_source_dir, allow_network)
                create_expansion_schema(connection)
                wordnet_id = add_source(connection, "wordnet-3.0", "Princeton WordNet 3.0",
                    EXPANSION_FILES["wordnet.zip"], "NLTK data revision 550b6625bcef1f2abff2ff770a5a0d272c9c6b2a",
                    "WordNet-3.0", "Princeton University WordNet 3.0")
                russian_id = add_source(connection, "openrussian-2021-08-09", "OpenRussian",
                    "https://github.com/Badestrand/russian-dictionary", "50e210c4803237779cb562bc1abcea529066031c",
                    "CC-BY-SA-4.0", "OpenRussian.org contributors")
                tatoeba_id = add_source(connection, "tatoeba-2026-09-26", "Tatoeba",
                    "https://downloads.tatoeba.org/exports/", "2026-09-26",
                    "CC-BY-2.0-FR", "Tatoeba contributors; individual contributor and sentence ID retained")
                expansion = {
                    "wordnet": import_wordnet(connection, expansion_source_dir / "wordnet.zip", wordnet_id),
                    "openrussian": import_openrussian(connection, expansion_source_dir, russian_id),
                    "tatoeba_en": import_tatoeba(connection, expansion_source_dir / "tatoeba-eng.tsv.bz2", "en", tatoeba_id),
                    "tatoeba_ru": import_tatoeba(connection, expansion_source_dir / "tatoeba-rus.tsv.bz2", "ru", tatoeba_id),
                }
                expansion["statistics"] = expanded_statistics(connection)
                expansion["source_files"] = {}
                for name, url in EXPANSION_FILES.items():
                    record = {
                        "url": url,
                        "bytes": (expansion_source_dir / name).stat().st_size,
                        "sha256": sha256(expansion_source_dir / name),
                        "acquisition_date": EXPANSION_ACQUISITION_DATE,
                    }
                    record.update(expansion_source_metadata(name))
                    expansion["source_files"][name] = record
                connection.execute("PRAGMA user_version=2")
            connection.execute("CREATE INDEX lookup ON entries (source, target, key)")
            if expansion is None:
                connection.execute("PRAGMA user_version=1")
            connection.execute("ANALYZE")
            connection.execute("PRAGMA optimize")
        staged.replace(output)
    manifest = dict(schema=2 if expansion_source_dir is not None else 1, sources=records, license="mixed-see-sources",
                    changes="TEI entries converted to indexed SQLite; stress-insensitive lookup keys added.",
                    sha256=hashlib.sha256(output.read_bytes()).hexdigest(), bytes=output.stat().st_size)
    if expansion_source_dir is not None:
        manifest["expansion"] = expansion
    (output.parent / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "build" / "lexicon-sources")
    parser.add_argument("--output", type=Path, default=ROOT / "vendor" / "lexicon" / "lexicon.sqlite3")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--expand-en-ru", action="store_true")
    parser.add_argument("--expansion-source-dir", type=Path,
                        default=ROOT / "build" / "lexical-sources" / "aw075")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_dir, args.output, args.allow_network,
                             args.expansion_source_dir if args.expand_en_ru else None), ensure_ascii=False, indent=2))
