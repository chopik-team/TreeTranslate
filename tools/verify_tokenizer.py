"""Development-only parity check against the official Transformers tokenizer."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", type=Path, default=Path("vendor/models/m2m100-418m-int8/tokenizer"))
    args = parser.parse_args()
    from transformers import M2M100Tokenizer
    from app.engine.backends.m2m100_tokenizer import LocalM2M100Tokenizer
    official = M2M100Tokenizer.from_pretrained(str(args.tokenizer.resolve()), local_files_only=True)
    local = LocalM2M100Tokenizer(args.tokenizer)
    cases = [("en", "Hello world."), ("ru", "Привет, мир."), ("zh", "你好世界"),
             ("ja", "日本語の文章。"), ("en", "file_name <tag> 123 😀")]
    for language, text in cases:
        official.src_lang = language
        expected = official.convert_ids_to_tokens(official.encode(text))
        actual = local.source_tokens(local.encode(text), language)
        assert actual == expected, f"Encoding mismatch: {language}"
        assert local.decode(actual) == official.decode(official.convert_tokens_to_ids(actual), skip_special_tokens=True), f"Decoding mismatch: {language}"
    print(f"Tokenizer parity: {len(cases)} cases passed (local artifacts only)")


if __name__ == "__main__":
    main()
