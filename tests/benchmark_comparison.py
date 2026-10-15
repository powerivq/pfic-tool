"""Generate a comparison report; discrepancies do NOT become passing assertions."""
from datetime import date
from pathlib import Path
import json
from pfic.tax import section1291,distribution_excess
from pfic.numbers import money

def main():
    due={y:date(y+1,4,15) for y in range(2011,2026)}
    cases=[]
    for name,amount,credit,reference in [
        ('sale',100000,0,{'16b':25858,'16c':28013,'16d':0,'16e':28013,'16f':10958}),
        ('distribution',75000,11250,{'16b':19393,'16c':21008,'16d':8339,'16e':12669,'16f':4995})]:
        r=section1291(amount,'2011-12-05','2025-06-01',2015,due,credit)
        comparisons=[{'line':k,'reference_whole_dollars':v,'program_whole_dollars':int(money(r[k],0)),'difference':int(money(r[k],0))-v,'matches':int(money(r[k],0))==v} for k,v in reference.items()]
        cases.append({'case':name,'reference_url':'https://www.andrewmitchel.com/resources/pfic/1291_fund_'+name,'inputs':{'purchase_date':'2011-12-05','event_date':'2025-06-01','first_pfic_year':2015,'excess_usd':amount,'excess_foreign_tax_credit_usd':credit},'comparisons':comparisons})
    result={'retrieved':'2026-10-15','validation_status':'DISCREPANCIES_RECORDED_NOT_CERTIFIED_MATCH','due_date_policy_for_comparison':'Explicit unadjusted April 15 of subsequent year; reference calculator does not expose its due-date assumptions','holding_period_policy':'Exclude acquisition day; include event day','rounding':'Whole dollars only at output; retain exact annual tax and FTC internally','cases':cases}
    target=Path(__file__).parents[1]/'docs'/'benchmark_comparison.json';target.write_text(json.dumps(result,indent=2)+'\n');print(target)
if __name__=='__main__':main()
