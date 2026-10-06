"""Explainable gates, not probability estimates."""
import re
from ..models import LinkType
from ..licenses import approved
from ..normalization import normalize


def assess(zh, ru, link_type, evidence, records, sources, config, excluded, exhausted, domain):
    weights = config['weights']; reasons = []; score = 0; status = 'REVIEW'
    if link_type in (LinkType.DIRECT, LinkType.CROSS_SOURCE):
        score += weights['direct']; reasons.append('shared_concept')
        if zh and ru:
            score += weights['preferred_pair']; reasons.append('preferred_zh_ru')
    else:
        score += weights['pivot']; reasons.append('pivot_requires_review')
    if any(v['kind'] == 'taxonomy' for v in evidence):
        score += weights['taxonomy']; reasons.append('taxonomy_path')
    groups = {sources[r['source']]['independence_group'] for r in records if approved(sources[r['source']])}
    agreeing = {sources[r['source']]['independence_group'] for r in records
                if zh in r['labels'].values() and ru in r['labels'].values() and approved(sources[r['source']])}
    if len(agreeing) > 1:
        score += weights['independent_agreement']; reasons.append('independent_source_agreement')
    if normalize(zh) in config['generic_terms'] or normalize(ru) in config['generic_terms']:
        score += weights['generic']; reasons.append('generic_term')
    if score >= config['verified_threshold'] and link_type in (LinkType.DIRECT, LinkType.CROSS_SOURCE):
        status = 'VERIFIED'
    if not zh or not ru:
        status = 'AUTO'; reasons.append('missing_preferred_pair')
    if not all(approved(sources[r['source']]) for r in records):
        status = 'REVIEW'; reasons.append('license_gate')
    if len({sources[r['source']]['license'] for r in records}) > 1:
        status = 'REVIEW'; reasons.append('mixed_license_family')
    if excluded:
        status = 'REJECTED'; reasons.append('proper_name_or_nonterm_class')
    if exhausted:
        status = 'REVIEW'; reasons.append('traversal_budget')
    if any(r.get('metadata', {}).get('review_only') for r in records):
        status = 'REVIEW'; reasons.append('source_review_only')
    if (zh and not re.search(r'[\u3400-\u9fff]', zh)) or re.search(r'\b[A-Z]{2,}\b|[A-Za-z]+[-_]?\d', zh + ' ' + ru):
        status = 'REVIEW'; reasons.append('acronym_or_model_identifier_keep_candidate')
    if len(zh) > 80 or len(ru) > 120:
        status = 'REVIEW'; reasons.append('suspicious_length')
    labels = ' '.join(v for r in records for v in r['labels'].values()).casefold()
    description = ' '.join(v for r in records for v in r['descriptions'].values()).casefold()
    if any(marker in labels for marker in config.get('review_label_markers', [])):
        status = 'REVIEW'; reasons.append('noncanonical_label_marker')
    if any(word in labels+' '+description for word in config.get('domain_review_keywords', {}).get(domain, [])):
        status = 'REVIEW'; reasons.append('domain_scope_requires_review')
    if any(word in description for word in ('brand name','product model','model of car','automobile model','company','scholarly article','patent')):
        status = 'REVIEW'; reasons.append('possible_proper_name')
    return max(0, min(100, score)), status, reasons
