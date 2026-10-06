"""Bounded scheduler-only adapter; frozen matrix runtime is unchanged."""
import argparse
import ast
import hashlib
import inspect
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import aw081_hardware_scaling_20 as experiment
from tools.aw081_speed_calibration_100 import save

original_controls = experiment.controls


def install_scheduler():
    from app.documents.archive_job import ArchiveJob
    source = textwrap.dedent(inspect.getsource(ArchiveJob._run))
    tree = ast.parse(source)
    before = ast.dump(tree)
    matches = []
    for context in ast.walk(tree):
        if not isinstance(context, ast.With):
            continue
        if not any(isinstance(item.context_expr, ast.Call) and
                   getattr(item.context_expr.func, 'id', '') == 'ZipFile'
                   for item in context.items):
            continue
        for node in context.body:
            if not (isinstance(node, ast.For) and isinstance(node.iter, ast.Name)
                    and node.iter.id == 'members'):
                continue
            # The other members loop creates empty directories after processing.
            # Identify the document loop by its existing child-job construction.
            if any(isinstance(child, ast.Call) and getattr(child.func, 'id', '') == 'DocumentJob'
                   for child in ast.walk(node)):
                matches.append(node)
    assert len(matches) == 1, 'Expected exactly one child-document processing loop'
    node = matches[0]
    old_iter = node.iter
    node.iter = ast.Call(func=ast.Name(id='_qa_hardware_sorted_members', ctx=ast.Load()),
                         args=[old_iter], keywords=[])
    modified = ast.dump(tree)
    node.iter = old_iter
    assert ast.dump(tree) == before
    node.iter = ast.Call(func=ast.Name(id='_qa_hardware_sorted_members', ctx=ast.Load()),
                         args=[old_iter], keywords=[])
    sample = json.loads((experiment.QA / 'sample_manifest.json').read_text('utf8'))
    metadata = {doc['member_path']: doc for doc in sample['documents']}

    def order_members(members):
        def key(member):
            doc = metadata[member.name]
            inspection = doc['source_inspection']
            likelihood = 2 if inspection['empty_native_pages'] or not inspection['native_alphabetic_chars'] else 1 if inspection['large_raster_pages'] else 0
            return likelihood, doc['pages'], doc['source_size'], member.name
        return sorted(members, key=key)

    namespace = dict(ArchiveJob._run.__globals__, _qa_hardware_sorted_members=order_members)
    ast.fix_missing_locations(tree)
    exec(compile(tree, '<QA hardware processing-loop order only>', 'exec'), namespace)
    ArchiveJob._run = namespace['_run']
    save(experiment.QA / 'easy_first_hook_validation.json', dict(status='PASS',
         modified_processing_loops=1,production_changes=False,
         original_ast_sha256=hashlib.sha256(before.encode()).hexdigest(),
         modified_ast_sha256=hashlib.sha256(modified.encode()).hexdigest(),
         only_change='processing-loop iterator; inventory, context sampling, reservation, directory-finalization and writer unchanged',
         frozen_runtime_script_unchanged=True))


def controls(configuration, engine, control, state):
    order = state['order']
    state['order'] = 'original'
    try:
        result = original_controls(configuration, engine, control, state)
    finally:
        state['order'] = order
    assert order == 'easy_first'
    install_scheduler()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run'])
    parser.add_argument('--label', required=True)
    parser.add_argument('--config', required=True, choices=list(experiment.CONFIGS))
    parser.add_argument('--order', choices=['easy_first'], required=True)
    args = parser.parse_args()
    experiment.controls = controls
    experiment.run(args.label, args.config, args.order)
