"""Publish the authorized AW0.86 technical release using existing Git credentials.

Never prints or persists authentication values; requires the already created tag.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'chopik-team/TreeTranslate'
TAG = 'AW0.86'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create', action='store_true')
    parser.add_argument('--asset', action='append', type=Path, default=[])
    args = parser.parse_args()
    commit = subprocess.check_output(['git', 'rev-parse', TAG+'^{commit}'], cwd=ROOT, text=True).strip()
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    filled = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            capture_output=True, text=True, env=env, timeout=25)
    fields = dict(line.split('=', 1) for line in filled.stdout.splitlines() if '=' in line)
    token = fields.get('password') or os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token:
        raise SystemExit('GitHub authentication unavailable; release remains prepared locally.')

    def request(url, method='GET', data=None, content_type='application/json'):
        assert urllib.parse.urlparse(url).hostname in {'api.github.com','uploads.github.com'}
        payload = json.dumps(data).encode() if isinstance(data, dict) else data
        req = urllib.request.Request(url, data=payload, method=method, headers={
            'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
            'Content-Type':content_type,'User-Agent':'TreeTranslate-AW0.86-freeze'})
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)

    endpoint = 'https://api.github.com/repos/'+REPO+'/releases'
    try:
        release = request(endpoint+'/tags/'+TAG)
    except urllib.error.HTTPError as error:
        if error.code != 404 or not args.create:
            raise SystemExit(f'GitHub release lookup failed: HTTP {error.code}') from None
        body_path = ROOT/'docs/releases/AW0.86.md'
        body = body_path.read_text('utf8')
        def absolute_link(match):
            relative = match.group(2)
            if relative.startswith(('http:', 'https:', '#')):
                return match.group(0)
            local = (body_path.parent/relative).resolve().relative_to(ROOT).as_posix()
            return '['+match.group(1)+'](https://github.com/'+REPO+'/blob/'+TAG+'/'+local+')'
        body = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', absolute_link, body)
        release = request(endpoint, 'POST', dict(tag_name=TAG,target_commitish=commit,
            name='TreeTranslate AW0.86',body=body,draft=False,prerelease=True,make_latest='false'))
    assert release['tag_name'] == TAG and not release['draft']
    uploaded = []
    for path in args.asset:
        path = path.resolve()
        assert path.is_relative_to(ROOT/'output/aw086') and path.is_file()
        existing = next((a for a in release['assets'] if a['name'] == path.name), None)
        if existing:
            assert existing['size'] == path.stat().st_size, 'Asset name collision; refusing overwrite'
            uploaded.append(existing)
            continue
        url = release['upload_url'].split('{',1)[0]+'?name='+urllib.parse.quote(path.name)
        mime = 'application/zip' if path.suffix == '.zip' else 'application/json' if path.suffix == '.json' else 'text/markdown'
        uploaded.append(request(url, 'POST', path.read_bytes(), mime))
    result = dict(status='PUBLISHED',tag=TAG,closing_commit=commit,release_id=release['id'],
        release_url=release['html_url'],prerelease=release['prerelease'],
        assets=[dict(name=a['name'],size=a['size'],url=a['browser_download_url']) for a in uploaded])
    output = ROOT/'output/aw086';output.mkdir(parents=True,exist_ok=True)
    (output/'release_publication.json').write_text(json.dumps(result,indent=2)+'\n','utf8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
