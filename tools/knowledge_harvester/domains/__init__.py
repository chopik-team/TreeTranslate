from collections import deque
import re


def keyword_matches(word, text):
    """Match whole English words, retaining source Chinese substring matching."""
    word=word.casefold()
    if re.search('[a-z]',word):
        forms=[re.escape(word)+r'(?:s|es)?']
        if word.endswith('y'):forms.append(re.escape(word[:-1])+'ies')
        return re.search(r'(?<![a-z])(?:'+'|'.join(forms)+r')(?![a-z])',text) is not None
    return word in text


def classify(con, concept, records, config):
    queue = deque([(concept, [])]); visited = set(); matches = {}; excluded = []
    roots = {root: domain for domain, rule in config['domains'].items() for root in rule['roots']}
    exhausted = False
    while queue:
        node, path = queue.popleft()
        if node in visited:
            continue
        if len(visited) >= config['max_traversal_nodes']:
            exhausted = True; break
        visited.add(node)
        if node in config['excluded_roots']:
            excluded.append(node)
        if node in roots:
            matches.setdefault(roots[node], []).append({'kind': 'taxonomy', 'root': node, 'path': path})
        if len(path) >= config['max_depth']:
            continue
        if config.get('pivot_version') == 2:
            mapped=con.execute('SELECT canonical FROM concept_aliases WHERE alias=?',(node,)).fetchone()
            if mapped:
                queue.append((mapped[0],[*path,[node,'exactMatch',mapped[0]]]))
        for row in con.execute('SELECT predicate,parent FROM relations WHERE child=? ORDER BY predicate,parent', (node,)):
            if row['predicate'] in config['relations']:
                queue.append((row['parent'], [*path, [node, row['predicate'], row['parent']]]))
    text = ' '.join(str(v) for r in records for v in [*r['labels'].values(), *r['descriptions'].values(), *r['definitions'], *r['domain_hints']]).casefold()
    for domain, rule in config['domains'].items():
        if domain not in matches:
            hints = [word for word in rule['keywords'] if keyword_matches(word,text)]
            if hints:
                matches[domain] = [{'kind': 'keyword_review_only', 'hints': hints}]
    return matches, excluded, exhausted
