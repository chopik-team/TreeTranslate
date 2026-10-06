from .models import MemoryMatch, Status, TRUST
from .normalization import normalize, compatible, template_key, SLOT
from .scoring import similarity, rank
from app.documents.pdf_fidelity import faithful_result, FidelityMismatch


def choose(rows, text, pair, domain, context, config):
    ranked = []
    normalized = normalize(text)
    for row, store in rows:
        if row['domain'] not in {domain, 'general'} or row['status'] in (Status.REJECTED, Status.AUTO):
            continue
        # Context-specific units must not leak into unrelated contexts.
        if row['context'] and row['context'] != context:
            continue
        target, score, reusable = row['target_text'], 1.0, True
        if row['is_template']:
            key = template_key(text)
            if not config['placeholder_enabled'] or not key or key[0] != row['source_normalized']:
                continue
            kind = 'placeholder'
            target = target.replace(SLOT, key[1])
        elif config['exact_enabled'] and text == row['source_text']:
            kind = 'exact'
        elif config['normalized_enabled'] and normalized == row['source_normalized'] and compatible(text, row['source_text']):
            kind = 'normalized'
        elif config['fuzzy_enabled']:
            # Bound quadratic edit comparison on long paragraphs.
            if max(len(normalized), len(row['source_normalized'])) > 2000:
                continue
            kind = 'fuzzy'
            score = similarity(normalized, row['source_normalized'])
            if score < config['fuzzy_threshold']:
                continue
            reusable = bool(config['fuzzy_reuse'] and score >= config['fuzzy_reuse_threshold']
                            and compatible(text, row['source_text']))
        else:
            continue
        try:
            # Guard applies even to exact user confirmations; no trust bypass.
            target = faithful_result(text, target)
            if not compatible(text, target):
                reusable = False
        except (FidelityMismatch, ValueError):
            reusable = False
        match = MemoryMatch(row['id'], row['source_text'], target, score, kind, pair,
                            TRUST[row['status']], row['domain'], reusable, store)
        ranked.append((rank(row, kind, score, domain, context, config, store), match))
    # Prefer safe outputs to unsafe higher-ranked alternatives.
    ranked.sort(key=lambda item: (item[1].reusable, item[0]), reverse=True)
    return tuple(match for _, match in ranked[:config['max_candidates']])
