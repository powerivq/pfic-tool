"""Import ONE supplied account/fund CSV; unresolved fields remain blank."""
import csv
import json
from pathlib import Path
from .model import COLUMNS
from .numbers import Q, InputError, dec


def import_legacy(source,destination):
    with open(source,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if not rows:raise InputError('Empty legacy CSV')
    if len({r.get('fund','') for r in rows})!=1:raise InputError('One fund per CSV required')
    out=[];issues=[];balance=Q(0)
    for number,r in enumerate(rows,2):
        kind=r['transaction_type'];identifier='legacy-'+str(number-1)
        def issue(field,message):issues.append({'id':identifier,'source_row':number,'field':field,'message':message})
        record={k:'' for k in COLUMNS}
        record.update(id=identifier,sequence=r.get('sequence_within_fund') or str(number-1),currency='CNY',units='0',fee='0',withholding='',account=r.get('source_account','default'),source=r.get('source_screenshots',''))
        if kind=='BUY':
            record.update(type='BUY',date=r.get('buy_confirmation_date',''),units=r['buy_units'],amount=r['buy_invested_CNY'],fee=r['fee_CNY'],withholding='0')
            if Q(r['buy_cash_paid_CNY'])!=Q(record['amount'])+Q(record['fee']):issue('amount','Cash paid differs from invested amount plus fee')
        elif kind=='SELL':
            record.update(type='SELL',date=r.get('sell_confirmation_date',''),units=r['sell_units'],amount=str(dec(Q(r['sell_net_proceeds_CNY'])+Q(r['fee_CNY']))),fee=r['fee_CNY'],withholding='0')
        elif kind=='DIVIDEND_CASH':
            record.update(type='DIVIDEND',date='',amount=r['cash_dividend_CNY'])
            issue('eligibility_date','Dividend entitlement date is absent')
            issue('withholding','Confirm gross dividend amount and withholding, including explicit zero')
        else:
            issue('type',f'Unsupported legacy transaction {kind}')
        if not record['date']:issue('date','Explicit confirmation date (or dividend payment date) required; other date fields are not substituted')
        balance+=Q(r['unit_change'])
        if balance!=Q(r['running_units']):issue('units','Recorded running balance does not reconcile')
        out.append(record)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=COLUMNS);writer.writeheader();writer.writerows(out)
    result={'source':str(source),'fund':rows[0]['fund'],'rows':len(rows),'ending_units':str(dec(balance)),'issues':issues,'ready':not issues}
    destination.with_suffix('.issues.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
