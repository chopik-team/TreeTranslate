"""Build-only M2M100 418M converter. Local sources by default; explicit network opt-in."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.model_artifacts import record_model

UPSTREAM = "facebook/m2m100_418M"
REVISION = "55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636"
SOURCE_FILES = ["config.json", "pytorch_model.bin", "sentencepiece.bpe.model", "vocab.json",
                "tokenizer_config.json", "special_tokens_map.json", "README.md", "generation_config.json"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=UPSTREAM, help="Local HF model directory, or official model id with --allow-network")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--revision", default=REVISION)
    parser.add_argument("--models-root", type=Path, default=Path("vendor/models"))
    parser.add_argument("--source-cache", type=Path, default=Path("build/model-sources/m2m100-418m"))
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "0" if args.allow_network else "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "0" if args.allow_network else "1"
    source = Path(args.source)
    provenance = str(source.resolve())
    version = "local-source"
    if not source.is_dir():
        if not args.allow_network or args.source != UPSTREAM:
            parser.error("Provide a local source directory; network requires --allow-network and the official model id.")
        from huggingface_hub import snapshot_download
        source = Path(snapshot_download(UPSTREAM, revision=args.revision, local_dir=args.source_cache,
                                        allow_patterns=SOURCE_FILES))
        provenance = f"https://huggingface.co/{UPSTREAM}/tree/{args.revision}"
        version = args.revision
    # Inference and conversion after artifact retrieval are strictly local.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    for file in SOURCE_FILES[:4]:
        if not (source / file).is_file():
            parser.error(f"Missing local source artifact: {file}")
    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != "m2m_100" or config.get("d_model") != 1024 or config.get("encoder_layers") != 12:
        parser.error("Expected official M2M100 418M architecture")
    root = args.models_root.resolve()
    output = root / "m2m100-418m-int8"
    if output.exists():
        parser.error("Output already exists; choose a different --models-root to avoid overwriting artifacts.")
    root.mkdir(parents=True, exist_ok=True)
    from ctranslate2.converters import TransformersConverter
    from transformers import M2M100Tokenizer
    card = source / "README.md"
    with tempfile.TemporaryDirectory(dir=root, prefix=".prepare-m2m100-") as temporary:
        stage = Path(temporary).resolve()
        if not stage.is_relative_to(root):
            raise ValueError("Preparation must stay within the model root")
        tokenizer = M2M100Tokenizer.from_pretrained(str(source.resolve()), local_files_only=True)
        tokenizer.save_pretrained(str(stage / "tokenizer"))
        # Explicit language metadata for the lightweight SentencePiece runtime adapter.
        (stage / "tokenizer" / "languages.json").write_text(
            json.dumps(sorted(tokenizer.lang_code_to_id), indent=2), encoding="utf-8")
        converter = TransformersConverter(str(source.resolve()), load_as_float16=False, trust_remote_code=False)
        converter.convert(str(stage / "model"), quantization="int8")
        if card.exists():
            shutil.copyfile(card, stage / "UPSTREAM_MODEL_CARD.md")
        # Publish only a completed artifact. On failure the temporary directory is removed.
        if not output.resolve().is_relative_to(root):
            raise ValueError("Output must stay within the model root")
        stage.rename(output)
    # The official model card declares MIT; never infer weights licensing from Transformers.
    license_text = "MIT (official model card)" if card.exists() and "license: mit" in card.read_text(encoding="utf-8").lower() else "UNKNOWN: review source weights license before distribution"
    row = record_model(root, output, model_id="m2m100-418m-int8", backend="m2m100",
                       version=version, source=provenance, languages=sorted(tokenizer.lang_code_to_id),
                       pairs=[], quantization="int8", license_text=license_text)
    print(json.dumps({"id": row["id"], "size": row["size"], "license": row["license"]}))


if __name__ == "__main__":
    main()
