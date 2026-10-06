"""Explicit developer commands; defaults never access the network or user databases."""
import argparse
import json
from pathlib import Path
import sys
from .config import load
from .storage import Store
from .ingest import ingest
from .linking import link
from .build.packs import build_packs
from .build.reports import report, export_queue
from .review import import_reviews
from .network import download
from .models import HarvestError
from .licenses import require_approved
from .provenance import canonical_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=Path('build/knowledge/harvest.db'))
    parser.add_argument('--config',type=Path)
    sub = parser.add_subparsers(dest='action',required=True)
    corpus=sub.add_parser('corpus-intake');corpus.add_argument('path',type=Path)
    corpus.add_argument('--corpus-id',required=True);corpus.add_argument('--language',required=True)
    corpus.add_argument('--origin',default='USER_PROVIDED');corpus.add_argument('--permission',default='REVIEW_REQUIRED')
    corpus.add_argument('--development-manifest',type=Path)
    native=sub.add_parser('corpus-harvest-manifest');native.add_argument('cache',type=Path);native.add_argument('manifest',type=Path);native.add_argument('output',type=Path)
    corpus_export=sub.add_parser('corpus-export');corpus_export.add_argument('output',type=Path)
    corpus_review=sub.add_parser('corpus-review');corpus_review.add_argument('path',type=Path)
    corpus_pack=sub.add_parser('corpus-build-pack');corpus_pack.add_argument('manifest',type=Path);corpus_pack.add_argument('output',type=Path)
    source = sub.add_parser('source-add');source.add_argument('metadata',type=Path)
    ingest_parser = sub.add_parser('ingest');ingest_parser.add_argument('path',type=Path)
    ingest_parser.add_argument('--source',required=True);ingest_parser.add_argument('--adapter',required=True,choices=['wikidata','cedict','agrovoc','wiktionary'])
    ingest_parser.add_argument('--sample',type=int)
    for action in ('link','classify','report'):
        sub.add_parser(action)
    for action in ('review-export','conflicts'):
        command = sub.add_parser(action);command.add_argument('output',type=Path);command.add_argument('--sample',type=int)
    review = sub.add_parser('review-import');review.add_argument('path',type=Path)
    build = sub.add_parser('build-packs');build.add_argument('output',type=Path);build.add_argument('--reverse',action='store_true')
    fetch = sub.add_parser('fetch');fetch.add_argument('url');fetch.add_argument('output',type=Path)
    fetch.add_argument('--source-metadata',type=Path,required=True)
    fetch.add_argument('--allow-network',action='store_true');fetch.add_argument('--max-bytes',type=int,default=64*1024*1024)
    for command in (source,ingest_parser,review,build,fetch,sub.choices['link'],sub.choices['classify']):
        command.add_argument('--dry-run',action='store_true')
    args = parser.parse_args(argv);store = Store(args.db);config = load(args.config)
    try:
        if args.action=='corpus-intake':
            from .corpus import intake
            result=intake(store,args.path,corpus_id=args.corpus_id,language=args.language,origin=args.origin,permission=args.permission,development_manifest=args.development_manifest)
        elif args.action=='corpus-harvest-manifest':
            from .corpus import harvest_manifest
            result=harvest_manifest(store,args.cache,args.manifest)
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
            result={'documents':result['documents'],'candidates':len(result['candidates']),'automatic_verified':0,'holdout_excluded':True}
        elif args.action=='corpus-export':
            from .corpus import export
            result={'candidates':export(store,args.output)}
        elif args.action=='corpus-review':
            from .corpus import review
            count=0
            for line in args.path.read_text('utf-8').splitlines():
                row=json.loads(line);review(store,row['candidate_id'],row['state'],reviewer=row['reviewer'],reason=row['reason'],evidence_sha256=row['evidence_sha256']);count+=1
            result={'reviews':count}
        elif args.action=='corpus-build-pack':
            from .corpus import reviewed_entries
            from app.glossary.packs import build_pack
            rows=list(reviewed_entries(store))
            if not rows:raise HarvestError('no_verified_redistributable_entries')
            result=build_pack(rows,json.loads(args.manifest.read_text('utf-8')),args.output)
        elif args.action=='source-add':result=store.source_add(json.loads(args.metadata.read_text('utf-8')),dry_run=args.dry_run)
        elif args.action=='ingest':result=ingest(store,args.path,args.source,args.adapter,config,sample=args.sample,dry_run=args.dry_run)
        elif args.action in ('link','classify'):result=link(store,config,dry_run=args.dry_run)
        elif args.action=='build-packs':result=build_packs(store,config,args.output,dry_run=args.dry_run,reverse=args.reverse)
        elif args.action=='report':result=report(store)
        elif args.action in ('review-export','conflicts'):result=export_queue(store,args.output,sample=args.sample,conflicts_only=args.action=='conflicts')
        elif args.action=='review-import':result=import_reviews(store,args.path,config,dry_run=args.dry_run)
        else:
            require_approved(json.loads(args.source_metadata.read_text('utf-8')))
            result=download(args.url,args.output,allow_network=args.allow_network,max_bytes=args.max_bytes,dry_run=args.dry_run)
    except (HarvestError,OSError,ValueError) as error:
        parser.exit(1,'Harvester: '+(str(error) if isinstance(error,HarvestError) else type(error).__name__)+'\n')
    print(canonical_json(result))


if __name__=='__main__':main()
