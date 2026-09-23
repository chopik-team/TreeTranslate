"""Explicit development/build step. Runtime never imports this downloader."""
import hashlib
import json
from pathlib import Path
import urllib.request

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


def main():
    root = Path(__file__).resolve().parents[1]
    api = 'https://api.github.com/repos/notofonts/noto-cjk/commits/main'
    with urllib.request.urlopen(api) as response:
        commit = json.load(response)['sha']
    base = f'https://raw.githubusercontent.com/notofonts/noto-cjk/{commit}/Sans/'
    source_url = base + 'Variable/TTF/Subset/NotoSansSC-VF.ttf'
    cache = root / 'build/pdf-font'
    target = root / 'assets/fonts'
    cache.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    source = cache / 'NotoSansSC-VF.ttf'
    urllib.request.urlretrieve(source_url, source)
    urllib.request.urlretrieve(base + 'LICENSE', target / 'OFL-NotoSansSC.txt')
    font = instantiateVariableFont(TTFont(source), {'wght': 400}, inplace=True)
    for record in font['name'].names:
        if record.nameID in {1, 3, 4, 6, 16, 17}:
            value = 'Regular' if record.nameID == 17 else 'TreeTranslate Sans'
            if record.nameID == 6:
                value = 'TreeTranslateSans-Regular'
            record.string = value.encode(record.getEncoding())
    output = target / 'TreeTranslateSans-Regular.ttf'
    font.save(output)
    cmap = font.getBestCmap()
    assert all(ord(c) in cmap for c in 'HelloПривет你好中文')
    metadata = {'source_url': source_url, 'commit': commit, 'license': 'SIL-OFL-1.1',
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'filename': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                'modification': 'Static weight 400 instance; renamed TreeTranslate Sans', 'glyphs': len(cmap)}
    (target / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
