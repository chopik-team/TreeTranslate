"""Build an explicitly supplied local terminology source; never download data."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.glossary.importer import source_rows
from app.glossary.packs import build_pack


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('manifest',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--user-package',action='store_true',help='Allow unknown license for a private user package')
    args=parser.parse_args()
    report=build_pack(source_rows(args.source),json.loads(args.manifest.read_text('utf-8')),args.output,official=not args.user_package)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
