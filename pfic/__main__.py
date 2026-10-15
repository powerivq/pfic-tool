import argparse
import json
from pathlib import Path
import sys
from . import Config,Valuation,TreasuryFX,calculate_csv,write_report,InputError
from .model import day
from .legacy import import_legacy


def main():
    parser=argparse.ArgumentParser(description='One-fund PFIC calculator: exact FIFO, §1291, §1296 and Form 8621 worksheets')
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('calculate');run.add_argument('csv');run.add_argument('--config',required=True);run.add_argument('--year',type=int);run.add_argument('--out',required=True);run.add_argument('--cache');run.add_argument('--offline',action='store_true')
    legacy=sub.add_parser('import-legacy');legacy.add_argument('csv');legacy.add_argument('--out',required=True)
    args=parser.parse_args()
    try:
        if args.command=='import-legacy':
            result=import_legacy(args.csv,args.out)
            print(f"Imported {result['rows']} rows; {len(result['issues'])} unresolved issues. See .issues.json")
            return 0 if result['ready'] else 2
        raw=json.loads(Path(args.config).read_text(encoding='utf-8'),parse_float=str)
        mappings=raw.pop('currency_countries',None)
        if args.year is not None:raw['tax_year']=args.year
        raw['valuations']={int(y):Valuation(**v) for y,v in raw.get('valuations',{}).items()}
        raw['due_dates']={int(y):day(d) for y,d in raw.get('due_dates',{}).items()}
        if raw.get('residency_opening_valuation') is not None:
            raw['residency_opening_valuation']=Valuation(**raw['residency_opening_valuation'])
        config=Config(**raw)
        fx=TreasuryFX(cache_dir=args.cache,currency_countries=mappings,offline=args.offline)
        result=calculate_csv(args.csv,config,fx)
        paths=write_report(result,args.out)
        print(f"Calculated {len(result['blocks'])} blocks for {config.tax_year}")
        for p in paths:print(p)
        return 0
    except (InputError,ValueError,TypeError,OSError) as e:
        print(f'BLOCKED: {e}',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
