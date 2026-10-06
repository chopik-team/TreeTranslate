"""Closed cross-reference syntax; unknown titles never become invented names."""
import re


def breadcrumb(text, lookup):
    """Every navigational node must be a known label or a literal title/code."""
    from app.documents.pdf_fidelity import preserve_title
    from app.documents.pdf_ocr_policy import protected_kind
    from app.glossary.constraints import validate_result
    from app.glossary.errors import ConstraintFailure
    nodes=text.split('>')
    if not 2<=len(nodes)<=8 or not re.search(r'[\u4e00-\u9fff]',text):
        return None
    result=[]
    for node in nodes:
        node=node.strip()
        if not node or len(node)>80 or re.search(r'[。；;?!？!]',node):
            return None
        if re.search(r'[\u4e00-\u9fff]',node):
            target=lookup(node)
            if not target:
                return None
        elif protected_kind(node) or preserve_title(node):
            target=node
        else:
            return None
        result.append(target)
    try:
        return validate_result(text,' > '.join(result))
    except ConstraintFailure:
        return None


def parts(text):
    return re.fullmatch(r'\s*[（(]\s*(?:请参阅|请参考|参阅|参考|参见)\s*(.{1,80}?)\s*[-–—]\s*'
                       r'[“"「](.{1,80}?)[“”"」]\s*[）)]\s*',text)


def is_reference(text):
    return bool(re.match(r'^\s*[（(]\s*(?:请参阅|请参考|参阅|参考|参见)',text)) and len(text) <= 200


def annotated(target):
    return target is not None and bool(re.fullmatch(r'См\. раздел «[^«»]+», название подраздела в источнике: «.+»\.',target))


def tagged_label(source, lookup, forms):
    """A reviewed whole noun plus a literal code and an optional system suffix."""
    tagged = re.fullmatch(r'(.{1,60}?)\s*([（(][A-Z][A-Z0-9-]{1,11}[）)])\s*(系统)?',source)
    if tagged is None:
        return None
    noun, marker, system = tagged.groups()
    target = lookup(noun.strip())
    form = forms.get(noun.strip())
    if not target:
        return None
    if system:
        if not form or not form.get('genitive') or form['base'].casefold()!=target.casefold():
            return None
        return 'система '+form['genitive']+' '+marker
    return target+' '+marker


def render(text, lookup, *, preserve_unknown_title=False, recover_title=None):
    parsed = parts(text)
    if parsed is None:
        # A missing final quote/parenthesis is repairable only for a whole
        # explicitly reviewed source alias. Unknown tails still fail closed.
        partial = re.fullmatch(r'\s*[（(]\s*(?:请参阅|请参考|参阅|参考|参见)\s*(.{1,80}?)\s*[-–—]\s*'
                               r'[“"「]([^“”"「」（）()]{1,80})\s*',text)
        if partial is None or recover_title is None or not recover_title(partial[2].strip()):
            return None
        section, title = (lookup(s.strip()) for s in partial.groups())
        return f'См. раздел «{section}», подраздел «{title}».' if section and title else None
    section, title = (lookup(s.strip()) for s in parsed.groups())
    if not section:
        return None
    if not title and preserve_unknown_title:
        return f'См. раздел «{section}», название подраздела в источнике: «{parsed[2]}».'
    if not title:
        return None
    return f'См. раздел «{section}», подраздел «{title}».'


def validate_source_title(source, target):
    """Validate one exact, explicitly annotated source title, not arbitrary residue.

    The default PDF validator remains strict. All atoms outside this title pass
    the same validator; the protected title itself must match character for
    character, including numbers, units, codes and punctuation.
    """
    from app.glossary.constraints import validate_result
    from app.glossary.errors import ConstraintFailure
    parsed = parts(source)
    rendered = re.fullmatch(r'См\. раздел «([^«»]+)», название подраздела в источнике: «(.+)»\.',target)
    marker = 'SOURCE_TITLE_LABEL'
    if (parsed is None or rendered is None or parsed[2] != rendered[2]
            or re.search(r'[\u4e00-\u9fff]',rendered[1]) or marker in source or marker in target):
        raise ConstraintFailure('source_title_reference')
    safe_source = source[:parsed.start(2)]+marker+source[parsed.end(2):]
    safe_target = target[:rendered.start(2)]+marker+target[rendered.end(2):]
    validated = validate_result(safe_source,safe_target)
    return validated.replace(marker,parsed[2])
