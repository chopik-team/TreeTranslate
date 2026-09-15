from threading import Event
from types import SimpleNamespace

from app.engine.backends.text_segments import translate_segments
from app.engine.types import InferenceOptions


def test_segmentation_preserves_all_input_and_blank_lines_without_ct2_truncation():
    seen = []
    def infer(batches):
        seen.extend(batches)
        return [SimpleNamespace(hypotheses=[batch]) for batch in batches]
    options = InferenceOptions("cpu", "int8", 1, 1, 6, 3, 20)
    text = "  abcdefghi\r\n\r\njklmn  "
    output = translate_segments(text, "zh", list, "".join, infer, options, Event())
    assert output == text
    assert "".join("".join(batch) for batch in seen) == "abcdefghijklmn"
    assert max(map(len, seen)) <= 3


def test_adjacent_sentences_keep_shared_context_for_model():
    seen = []
    def infer(batches):
        seen.extend(batches)
        return [SimpleNamespace(hypotheses=[["Первая фраза. Вторая фраза."]]) for _ in batches]
    options = InferenceOptions("cpu", "int8", 1, 1, 100, 20, 50)
    output = translate_segments("第一句。第二句。", "ru", list, "".join, infer, options, Event())
    assert seen == [list("第一句。第二句。")]
    assert output == "Первая фраза. Вторая фраза."


def test_abbreviations_and_pronouns_are_not_cut_into_isolated_sentences():
    seen = []
    def infer(batches):
        seen.extend(batches)
        return [SimpleNamespace(hypotheses=[batch]) for batch in batches]
    options = InferenceOptions("cpu", "int8", 1, 1, 192, 192, 512)
    text = "Dr. Smith lives in the U.S. He works there."
    assert translate_segments(text, "en", list, "".join, infer, options, Event()) == text
    assert seen == [list(text)]
