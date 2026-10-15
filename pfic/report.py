"""Self-contained printable HTML and exact machine-readable worksheets."""
from pathlib import Path
from fractions import Fraction
from decimal import Decimal
from datetime import date
from html import escape
import json
from .numbers import money, encode, dec


def _show(value, field=""):
    precision_field = any(k in field.lower() for k in ("units", "rate", "factor", "foreign_per_usd"))
    if value is None:return '—'
    if isinstance(value,Fraction):
        exact=f'{value.numerator}/{value.denominator}'
        return f'<span title="Exact: {exact}">{str(dec(value)) if precision_field else money(value, 0)}</span>'
    if isinstance(value,Decimal):return f'<span title="{value}">{str(value) if precision_field else money(value, 0)}</span>'
    if isinstance(value,(dict,list,tuple)):
        return '<details><summary>Details</summary><pre>'+escape(json.dumps(encode(value),ensure_ascii=False,indent=2))+'</pre></details>'
    return escape(str(value))


def _table(rows,columns):
    return '<table><thead><tr>'+''.join('<th>'+escape(c.replace('_',' '))+'</th>' for c in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+_show(r.get(c), str(r.get("field", r.get("field_or_form_line", r.get("item", c)))))+'</td>' for c in columns)+'</tr>' for r in rows)+'</tbody></table>'


def write_report(report,output_dir):
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    json_path=output_dir/'form8621.json'
    json_path.write_text(json.dumps(encode(report),ensure_ascii=False,indent=2),encoding='utf-8')
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Form 8621 worksheets</title><style>body{font:15px/1.5 system-ui,sans-serif;color:#172b40;max-width:1250px;margin:40px auto;padding:0 24px}h1,h2,h3{line-height:1.2}h1{font-size:30px}h2{margin-top:36px;border-bottom:2px solid #a7c5d6;padding-bottom:10px}h3{margin-top:24px}td{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;margin:12px 0 22px;font-variant-numeric:tabular-nums}td,th{text-align:left;padding:8px;border-bottom:1px solid #dbe3e8;vertical-align:top}th{background:#edf3f7;font-size:12px}pre{white-space:pre-wrap;font-size:11px;max-height:500px;overflow:auto}.meta{color:#496578}.note{background:#fff5da;padding:15px;border-radius:6px}.block{break-before:page}small{color:#496578}@media print{body{margin:0;max-width:none;font-size:10px}details[open] pre{max-height:none}table{font-size:9px}h2{font-size:18px}}</style><body>']
    parts.append('<h1>'+escape(report['fund_name'])+' · '+str(report['tax_year'])+'</h1>')
    parts.append('<p class="meta">Form 8621 calculation worksheets · form revision '+report['form_revision']+' · FIFO · '+str(len(report['blocks']))+' blocks</p>')
    parts.append('<p class="note">Calculation schedules and line references, not a completed official IRS PDF. Dollar displays round to whole dollars (half up); calculations retain full precision. Rounded component rows may differ from an independently rounded total. Exact values are in form8621.json. Hover over amounts for precision details.</p>')
    parts.append('<p class="note">'+escape(report.get('benchmark_status',''))+'</p>')
    parts.append('<h2>Fund totals (USD)</h2>'+_table([{'item':k,'amount':v} for k,v in report['summary_usd'].items()],['item','amount']))
    parts.append('<p>Remaining units: '+escape(str(report['ending_units']))+'</p>')
    parts.append('<ul>'+''.join('<li>'+escape(n)+'</li>' for n in report['notes'])+'</ul>')
    for b in report['blocks']:
        parts.append('<section class="block"><h2>Block '+escape(b['block_id'])+'</h2>')
        metadata={k:v for k,v in b.items() if k not in ('worksheets','basis_history','distribution_history')}
        parts.append(_table([{'field':k,'value':v} for k,v in metadata.items()],['field','value']))
        if not b['worksheets']:parts.append('<p>No sale, distribution or MTM worksheet for this block in the selected year.</p>')
        for w in b['worksheets']:
            parts.append('<h3>'+escape(w['kind'].replace('_',' ').title())+' · '+escape(str(w.get('transaction_id',w.get('date',''))))+'</h3>')
            parts.append(_table([{'field_or_form_line':k,'value':v} for k,v in w.items() if k!='tax'],['field_or_form_line','value']))
            if w.get('tax'):
                tax=w['tax']
                parts.append('<h3>Part V · line 16a allocation</h3>')
                parts.append(_table(tax['annual_allocations'],['year','start_inclusive','end_inclusive','days','category','allocated_excess_usd','highest_tax_rate','gross_tax','allocated_credit','credit_used','net_tax','interest']))
                parts.append(_table([{'line':k,'USD':tax[k]} for k in ('16b','16c','16d','16e','16f')],['line','USD']))
                for a in tax['annual_allocations']:
                    if a['interest_segments']:
                        parts.append('<details><summary>'+str(a['year'])+' interest calculation</summary>'+_table(a['interest_segments'],['start_inclusive','end_exclusive','days','annual_rate','year_days','factor'])+'</details>')
        if b['basis_history']:
            parts.append('<h3>Basis and MTM history</h3>'+_show(b['basis_history']))
        if b['distribution_history']:
            parts.append('<h3>Distribution history used for future thresholds</h3>'+_table(b['distribution_history'],['distribution_id','date','currency','gross_local','included_local','excluded_prior_pfic_local','us_taxable_event','lookback_only']))
        parts.append('</section>')
    parts.append('<h2>Exchange rate audit</h2>'+_table(report['fx_audit'],['currency','transaction_date','effective_date','foreign_per_usd','record_date','policy','source']))
    parts.append('<h2>Run configuration</h2>'+_show(encode(report['config'])))
    if report.get('input_sha256'):parts.append('<p>Input SHA-256: '+escape(report['input_sha256'])+'</p>')
    parts.append('</body></html>')
    html_path=output_dir/'form8621.html';html_path.write_text(''.join(parts),encoding='utf-8')
    return html_path,json_path
