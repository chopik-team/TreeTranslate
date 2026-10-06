"""Bounded paragraph context, preserving separators and avoiding CT2 truncation.

Keep neighbouring sentences together, including abbreviations and pronoun context.
Oversized paragraphs still use explicit token chunks; no external SBD model.
"""
import re
from threading import Event

from app.engine.backends.base_backend import check_cancelled
from app.engine.errors import TranslationError
from app.engine.types import InferenceOptions


def translate_segments(text, target, encode, decode, infer, options: InferenceOptions, cancelled: Event,
                       *, question_boundaries=False):
    layout = []
    batches = []
    batch_indexes = {}  # Request-local only; identical model input has identical decoding context.
    # Keep whitespace (including blank paragraphs) outside the model.
    # Argos can stop after a question and silently omit the following prohibition.
    # Split only unambiguous ?/! whitespace boundaries; keep periods, abbreviations,
    # paragraph separators and the default multilingual context behavior unchanged.
    boundary = r"(\r\n|\r|\n|(?<=[?!！？])[ \t]+)" if question_boundaries else r"(\r\n|\r|\n)"
    for segment in re.split(boundary, text):
        if segment is None or segment == "":
            continue
        if not segment.strip():
            layout.append(segment)
            continue
        leading = segment[:len(segment) - len(segment.lstrip())]
        trailing = segment[len(segment.rstrip()):]
        tokens = encode(segment.strip())
        indexes = []
        for offset in range(0, len(tokens), options.max_input_tokens):
            chunk = tokens[offset:offset + options.max_input_tokens]
            key = tuple(chunk)
            index = batch_indexes.get(key)
            if index is None:
                index = len(batches)
                batch_indexes[key] = index
                batches.append(chunk)
            indexes.append(index)
        layout.append((leading, indexes, trailing))
    translated = []
    # Bound each native call as well as the internal CT2 batch; cancellation is
    # observed between calls and never forcibly kills a C++ inference thread.
    start = 0
    while start < len(batches):
        check_cancelled(cancelled)
        end, count = start, 0
        while end < len(batches) and (end == start or count + len(batches[end]) <= options.batch_tokens):
            count += len(batches[end])
            end += 1
        results = infer(batches[start:end])
        check_cancelled(cancelled)
        for result in results:
            tokens = result.hypotheses[0]
            if len(tokens) >= options.max_decoding_length:
                raise TranslationError("Перевод фрагмента превысил допустимую длину. Разделите текст на части.")
            translated.append(decode(tokens))
        start = end
    separator = "" if target in {"zh", "ja"} else " "
    output = []
    previous_was_translation = False
    for item in layout:
        if isinstance(item, str):
            output.append(item)
            previous_was_translation = False
        else:
            leading, indexes, trailing = item
            if previous_was_translation and not leading and output and not output[-1][-1:].isspace():
                output.append(separator)
            output.append(leading + separator.join(translated[i] for i in indexes) + trailing)
            previous_was_translation = True
    return "".join(output)
