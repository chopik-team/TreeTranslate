"""Local SentencePiece/token vocabulary adapter for the official M2M100 format.

Source: Transformers M2M100Tokenizer and the CT2 M2M100 guide. No HF import or hub.
Build-time parity checks compare this adapter to the official tokenizer.
"""
import json
from pathlib import Path

from app.engine.errors import ModelCorruptedError


class LocalM2M100Tokenizer:
    def __init__(self, root: Path) -> None:
        import sentencepiece
        try:
            self.vocab = json.loads((root / "vocab.json").read_text(encoding="utf-8"))
            self.languages = frozenset(json.loads((root / "languages.json").read_text(encoding="utf-8")))
            self.processor = sentencepiece.SentencePieceProcessor(model_file=str(root / "sentencepiece.bpe.model"))
            if not {"<unk>", "<s>", "</s>", "<pad>"} <= self.vocab.keys():
                raise ValueError("vocab")
        except (OSError, ValueError, RuntimeError):
            raise ModelCorruptedError() from None

    def encode(self, text: str) -> list[str]:
        return [piece if piece in self.vocab else "<unk>" for piece in self.processor.encode(text, out_type=str)]

    def source_tokens(self, pieces: list[str], language: str) -> list[str]:
        return [f"__{language}__", *pieces, "</s>"]

    def decode(self, pieces: list[str]) -> str:
        special = {"<s>", "</s>", "<pad>"} | {f"__{code}__" for code in self.languages}
        # Same SentencePiece conversion as the official slow tokenizer; do not
        # decode numeric SP ids (HF vocabulary ids have a different mapping).
        return self.processor.decode_pieces([p for p in pieces if p not in special]).strip()
