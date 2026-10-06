"""Conservative normalization; original labels always remain stored."""
import unicodedata


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).translate(str.maketrans({'“':'"', '”':'"', '‘':"'", '’':"'"})).split())


def preferred(labels, language):
    keys = ('zh-hans', 'zh-cn', 'zh', 'zh-hant', 'zh-tw') if language == 'zh' else (language,)
    return next((labels[k] for k in keys if labels.get(k)), '')


def variants(record, language):
    # Only source-declared forms. No lossy conversion or inferred equivalence.
    values = []
    for key, value in record['labels'].items():
        if key.split('-')[0] == language:
            values.append(value)
    for key, aliases in record['aliases'].items():
        if key.split('-')[0] == language:
            values.extend(aliases)
    return sorted(set(values))
