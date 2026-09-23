"""Explicit developer-only download/import of revision-pinned official Paddle models."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    'PP-OCRv6_small_det': ('106c97591b235f607453300d9fc8c1cad1b25488', 'detection', ['zh', 'en', 'ru']),
    'PP-OCRv6_small_rec': ('bd619643acac4b9650c040234da8d944476ee3f1', 'recognition', ['zh', 'en']),
    'cyrillic_PP-OCRv5_mobile_rec': ('712d2d65556ccc1ea7b5d2bb232b018838b6a3ab', 'recognition', ['ru']),
    'PP-DocLayout_plus-L': ('aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d', 'layout', ['zh', 'en', 'ru']),
    'PP-LCNet_x1_0_doc_ori': ('d3b95a6dff5fe8a94f2748e12b61cb26818a0df8', 'orientation', ['zh', 'en', 'ru']),
    'PP-LCNet_x1_0_table_cls': ('2fa6323e7dab88fa883081db1460995f46af2922', 'table', ['zh','en','ru']),
    'SLANeXt_wired': ('763069fcda6a065f2171753205a32bf899a88d15', 'table', ['zh','en','ru']),
    'SLANet_plus': ('bae6e5f8c3c4e7da0c0b7639fdf3228fe76184e2', 'table', ['zh','en','ru']),
    'RT-DETR-L_wired_table_cell_det': ('e2bd53c06b3a815d86acbf5c6779dada58819cfe', 'table', ['zh','en','ru']),
    'RT-DETR-L_wireless_table_cell_det': ('25ca86356a601c877476bb0dcc5fd09153d9d64d', 'table', ['zh','en','ru']),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-network', action='store_true')
    parser.add_argument('--local', type=Path, help='Directory with model-id subdirectories and upstream README')
    parser.add_argument('--root', type=Path, default=ROOT / 'vendor/models/ocr')
    parser.add_argument('--models', nargs='+', choices=MODELS, default=list(MODELS))
    args = parser.parse_args()
    if not args.allow_network and args.local is None:
        parser.error('Use --local or explicitly authorize --allow-network (build only)')
    args.root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.root / 'models_manifest.json'
    rows = {r['id']: r for r in json.loads(manifest_path.read_text('utf-8'))['models']} if manifest_path.exists() else {}
    for name in args.models:
        revision, role, languages = MODELS[name]
        source = f'https://huggingface.co/PaddlePaddle/{name}/tree/{revision}'
        folder = args.root / 'paddle' / role / name
        folder.mkdir(parents=True, exist_ok=True)
        for filename in ('README.md', 'inference.json', 'inference.pdiparams', 'inference.yml'):
            destination = folder / filename
            if args.local:
                shutil.copyfile(args.local / name / filename, destination)
            elif not destination.exists():
                url = f'https://huggingface.co/PaddlePaddle/{name}/resolve/{revision}/{filename}'
                part = destination.with_suffix(destination.suffix + '.partial')
                try:
                    with urllib.request.urlopen(url, timeout=120) as response, part.open('wb') as out:
                        shutil.copyfileobj(response, out)
                    part.replace(destination)
                finally:
                    part.unlink(missing_ok=True)
        card = (folder / 'README.md').read_text('utf-8')
        license_name = 'Apache-2.0' if 'license: apache-2.0' in card else 'UNRESOLVED: redistribution blocked'
        if license_name != 'Apache-2.0':
            raise RuntimeError(f'Unresolved model license: {name}; manifest publication blocked')
        files = [dict(path=p.name, size=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                 for p in sorted(folder.iterdir()) if p.is_file()]
        rows[name] = dict(id=name, backend='paddle', upstream_id='PaddlePaddle/'+name, version=revision,
                          source=source, path=folder.relative_to(args.root).as_posix(), role=role,
                          languages=languages, scripts=['Cyrillic'] if languages == ['ru'] else ['Han', 'Latin'],
                          devices=['cpu', 'gpu'], format='Paddle inference JSON + pdiparams', quantization='FP32',
                          architecture=name, pairs=[], license=license_name, files=files, size=sum(f['size'] for f in files))
        manifest_path.write_text(json.dumps(dict(schema_version=1, models=list(rows.values())), indent=2), 'utf-8')
        metadata = ROOT / 'vendor/model-metadata/ocr' / name
        metadata.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / 'README.md', metadata / 'README.md')
        print(name, rows[name]['size'], license_name, flush=True)
    shutil.copyfile(manifest_path, ROOT / 'vendor/model-metadata/ocr/models_manifest.json')


if __name__ == '__main__':
    main()
