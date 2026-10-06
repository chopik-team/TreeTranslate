from difflib import SequenceMatcher
import re

from .models import TRUST


def similarity(left, right):
    # Character component covers Chinese, word component helps spaced scripts.
    chars = SequenceMatcher(None, left, right, autojunk=False).ratio()
    a, b = set(re.findall(r'\w+', left)), set(re.findall(r'\w+', right))
    words = len(a & b) / max(1, len(a | b))
    if re.search(r'[\u3400-\u9fff]', left + right):
        return chars
    return .8 * chars + .2 * words


def rank(row, match_type, score, domain, context, config, store):
    exactness = {'exact': 4, 'normalized': 3, 'placeholder': 2, 'fuzzy': 1}[match_type]
    # User-confirmed alternatives lead within an equal match level.
    confirmation = int(store == 'user' and row['confirmed_by_user'])
    affinity = (config['domain_weight'] * (row['domain'] == domain)
                + config['trust_weight'] * TRUST[row['status']] + .05 * (bool(context) and row['context'] == context))
    return exactness, confirmation, affinity, score, row['quality'], row['use_count'], row['updated_at'], -row['id']
