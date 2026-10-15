"""One fund, one run. FIFO partitions followed by per-block tax calculations."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, localcontext
from collections import defaultdict
from pathlib import Path
import hashlib
from .model import Config, Transaction, read_csv, ZERO
from .numbers import Q, InputError
from .rates import TreasuryFX
from .tax import holding_days, section1291, mtm_year_end, mtm_sale, distribution_excess, allocation_periods, residency_mtm_sale

@dataclass(frozen=True)
class Block:
    id: str
    buy: Transaction
    units: object
    sale: Transaction | None = None

    @property
    def purchase_cost(self):
        return (self.buy.amount+self.buy.fee)*self.units/self.buy.units

    @property
    def proceeds(self):
        return (self.sale.amount-self.sale.fee)*self.units/self.sale.units if self.sale else None


def partition(transactions):
    """Partition original acquisitions into disjoint sold blocks and final holdings."""
    transactions=sorted(transactions,key=lambda t:(t.date,t.sequence,t.account,t.id))
    ids=set();keys=set();available=defaultdict(list);blocks=[]
    for t in transactions:
        if t.id in ids:raise InputError(f'Duplicate transaction ID: {t.id}')
        if (t.account,t.key) in keys:raise InputError(f'Ambiguous same-day ordering: {t.id}')
        ids.add(t.id);keys.add((t.account,t.key))
        if t.type in ('BUY','REINVEST'):
            available[t.account].append([t,t.units])
        elif t.type=='SELL':
            remaining=t.units
            for lot in available[t.account]:
                buy,units=lot
                if not units:continue
                take=min(units,remaining)
                blocks.append(Block(f'{buy.id}/sold/{t.id}',buy,take,t))
                lot[1]-=take;remaining-=take
                if remaining==0:break
            if remaining:raise InputError(f'{t.id}: oversell of {remaining} units in account {t.account}')
    for lots in available.values():
        for buy,units in lots:
            if units:blocks.append(Block(f'{buy.id}/held',buy,units))
    return sorted(blocks,key=lambda b:(b.buy.key,b.buy.account,b.id))


def allocate_dividends(transactions,blocks):
    """Eligibility is a snapshot; payment date separately controls income and FX."""
    allocations=defaultdict(list)
    for d in transactions:
        if d.type!='DIVIDEND':continue
        trades=[t for t in transactions if t.account==d.account and t.type!='DIVIDEND' and t.date==d.eligibility_date]
        if trades and d.eligibility_sequence is None:
            raise InputError(f'{d.id}: trades on eligibility date; supply eligibility_sequence (inclusive cutoff)')
        cutoff=(d.eligibility_date,d.eligibility_sequence if d.eligibility_sequence is not None else 10**30)
        eligible=[b for b in blocks if b.buy.account==d.account and b.buy.key<=cutoff and (b.sale is None or b.sale.key>cutoff)]
        total=sum((b.units for b in eligible),ZERO)
        if total<=0:raise InputError(f'{d.id}: dividend has no eligible shares')
        for b in eligible:
            allocations[b.id].append({'transaction':d,'amount':d.amount*b.units/total,'withholding':d.withholding*b.units/total,'eligible_units':b.units,'total_eligible_units':total})
        if sum((d.amount*b.units/total for b in eligible),ZERO)!=d.amount:
            raise AssertionError('Dividend conservation failure')
    return allocations


def _validate_links(transactions):
    byid={t.id:t for t in transactions};used=defaultdict(lambda:ZERO)
    for t in transactions:
        if t.type=='REINVEST':
            d=byid.get(t.linked_dividend_id)
            if not d or d.type!='DIVIDEND' or d.account!=t.account or d.currency!=t.currency or t.key<=d.key:
                raise InputError(f'{t.id}: invalid reinvestment link; dividend must precede reinvestment in same currency/account')
            used[d.id]+=t.amount+t.fee
            if used[d.id]>d.amount-d.withholding:
                raise InputError(f'{t.id}: reinvestment exceeds net dividend')


def _regime(config,b,year):
    if config.regime=='1291' or year<config.election_year:return '1291'
    start_year=(b.buy.date+timedelta(days=1)).year
    if year==config.election_year and max(start_year,config.effective_pfic_start.year)<year:return 'transition'
    return 'mtm'


def calculate(transactions,config,fx=None):
    """Return an auditable report. Accepts Transaction objects; no file I/O required.

    Full ordinary acquisition/dividend history; direct individual calendar-year
    ownership with one uninterrupted U.S.-person period. No QEF, transfers, PFIC cessation,
    corporate actions, return-of-capital distributions, or automatic elections.
    """
    if not isinstance(config,Config):raise InputError('config must be Config')
    txs=list(transactions)
    if not all(isinstance(t,Transaction) for t in txs):raise InputError('Expected Transaction objects')
    if not txs:raise InputError('Empty transaction history')
    if len({t.id for t in txs})!=len(txs):raise InputError('Duplicate transaction IDs')
    # Later records are retained only for possible wash-sale detection.
    end=date(config.tax_year,12,31)
    active=sorted([t for t in txs if t.date<=end],key=lambda t:(t.date,t.sequence,t.account,t.id))
    if not active:raise InputError('No transactions on/before selected tax year')
    if any(t.type=='DIVIDEND' for t in active) and not config.ordinary_dividends_confirmed:
        raise InputError('Confirm these are ordinary distributions, not capital returns or stock dividends')
    _validate_links(active)
    blocks=partition(active)
    held=sum((b.units for b in blocks if b.sale is None),ZERO)
    if config.ending_units is not None and held!=config.ending_units:
        raise InputError(f'Ending units mismatch: calculated {held}, expected {config.ending_units}')
    if config.regime=='mtm' and config.election_year<=config.tax_year:
        election_end=date(config.election_year,12,31)
        if not any(b.buy.date<=election_end and (b.sale is None or b.sale.date>election_end) for b in blocks):
            raise InputError('No shares held at the close of the proposed MTM election year; verify election validity')
    allocations=allocate_dividends(active,blocks)
    fx=fx or TreasuryFX()
    output=[]
    for b in blocks:
        basis=fx.usd(b.purchase_cost,b.buy.currency,b.buy.date)
        original_basis=basis;general_basis=basis;unreversed=ZERO;history=[];works=[];dist_history=[]
        pre_residency=b.buy.date<config.us_person_since
        owned_at_residency=b.sale is None or b.sale.date>=config.us_person_since
        residency_mtm=(pre_residency and owned_at_residency and config.regime=='mtm'
                       and config.election_year==config.us_person_since.year
                       and config.election_year<=config.tax_year)
        if residency_mtm:
            if config.us_person_since!=date(config.us_person_since.year,1,1):
                raise InputError('First-residency-year MTM with midyear residency requires reviewed transition treatment; use 1291 or a later valid election')
            if config.effective_pfic_start!=config.us_person_since:
                raise InputError('Residency MTM uplift requires PFIC status at residency start')
            valuation=config.residency_opening_valuation
            if valuation is None:
                raise InputError('residency_opening_valuation required for first-residency-year MTM')
            opening_fmv=fx.usd(valuation.unit_value*b.units,valuation.currency,config.us_person_since)
            basis=max(general_basis,opening_fmv)
            history.append({'action':'residency_mtm_opening','date':config.us_person_since,
                            'opening_fmv_usd':opening_fmv,'general_basis_usd':general_basis,
                            'mtm_basis_usd':basis,'unreversed_inclusions':ZERO})
        distributions=allocations.get(b.id,[])
        # Preserve original acquisition even when §1296 resets PFIC holding periods.
        for year in range(b.buy.date.year,config.tax_year+1):
            mode=_regime(config,b,year)
            if b.sale and config.regime=='mtm' and b.sale.date.year<config.election_year:
                mode='1291'
            current=[d for d in distributions if d['transaction'].date.year==year]
            if current:
                previous=[h for h in dist_history if year-3<=h['date'].year<year]
                currencies={d['transaction'].currency for d in current}|{h['currency'] for h in previous}
                currency=next(iter(currencies)) if len(currencies)==1 else 'USD'
                def normalize(amount,ccy,when):return amount if ccy==currency else fx.usd(amount,ccy,when)
                current_total=sum((normalize(d['amount'],d['transaction'].currency,d['transaction'].date) for d in current),ZERO)
                prior_total=sum((normalize(h['included_local'],h['currency'],h['date']) for h in previous),ZERO)
                preceding=min(3,max(0,year-(b.buy.date+timedelta(days=1)).year))
                threshold_result=distribution_excess(current_total,prior_total,preceding)
                average=threshold_result['15c'];threshold=threshold_result['15d']
                excess=threshold_result['excess'] if mode!='mtm' else ZERO
                for d in current:
                    tx=d['transaction'];norm=normalize(d['amount'],tx.currency,tx.date)
                    fraction=excess/current_total if current_total else ZERO
                    taxable=tx.date>=config.us_person_since
                    pfic_event=taxable and tx.date>=config.effective_pfic_start
                    # Preserve annual testing/apportionment, but pre-residency events
                    # are history only, and pre-PFIC resident events are ordinary dividends.
                    event_fraction=fraction if pfic_event else ZERO
                    event_excess_local=d['amount']*event_fraction
                    event_excess=fx.usd(event_excess_local,tx.currency,tx.date)
                    gross_usd=fx.usd(d['amount'],tx.currency,tx.date)
                    nonexcess_usd=gross_usd-event_excess
                    periods=allocation_periods(b.buy.date,tx.date,config.first_pfic_year,config.effective_pfic_start) if event_excess else []
                    prior_pfic_days=sum(p['days'] for p in periods if p['category']=='prior_PFIC')
                    excluded_fraction=Q(prior_pfic_days)/sum(p['days'] for p in periods) if periods else ZERO
                    included_local=d['amount']-event_excess_local*excluded_fraction
                    dist_history.append({'distribution_id':tx.id,'date':tx.date,'currency':tx.currency,'gross_local':d['amount'],'included_local':included_local,'excluded_prior_pfic_local':d['amount']-included_local,'us_taxable_event':taxable,'lookback_only':not taxable})
                    if year==config.tax_year and taxable:
                        tax_credit=fx.usd(d['withholding']*event_fraction,tx.currency,tx.date) if config.claim_foreign_tax_credit else ZERO
                        tax=section1291(event_excess,b.buy.date,tx.date,config.first_pfic_year,config.due_dates,tax_credit,pfic_start_date=config.effective_pfic_start) if event_excess else None
                        record={'kind':'dividend','transaction_id':tx.id,'payment_date':tx.date,'eligibility_date':tx.eligibility_date,'eligible_units':d['eligible_units'],'total_eligible_units':d['total_eligible_units'],'currency':currency,'distribution_currency':tx.currency,'allocated_dividend_local':d['amount'],'allocated_dividend_usd':gross_usd,'nonexcess_dividend_usd':nonexcess_usd,'withholding_local':d['withholding'],'withholding_usd':fx.usd(d['withholding'],tx.currency,tx.date),'current_year_foreign_tax_credit_candidate_usd':(fx.usd(d['withholding']*(1-event_fraction),tx.currency,tx.date)+(tax['current_year_credit_candidate'] if tax else ZERO)) if config.claim_foreign_tax_credit else ZERO,'15a':current_total,'15b':prior_total if preceding else None,'15c':average if preceding else None,'15d':threshold if preceding else None,'annual_excess':excess,'event_excess_calculation_currency':norm*event_fraction,'event_excess_usd':event_excess,'prior_years_in_average':preceding,'tax':tax,'regime':mode,'history_included_local':included_local}
                        # 15a-d are annual block totals repeated for reference, never summed across events.
                        if config.tax_year>=2025:
                            record['15e(1)']=excess;record['15e(2)']=event_excess
                        else:
                            record['15e']=excess
                            record['15e_usd_for_16a']=event_excess
                        if mode=='mtm':
                            record['form_part']='ordinary_dividend_outside_Part_IV'
                        else:record['form_part']='V'
                        works.append(record)
            if b.sale and b.sale.date.year==year:
                proceeds=fx.usd(b.proceeds,b.sale.currency,b.sale.date);gain=proceeds-general_basis
                # A wash-sale adjustment changes basis and subsequent PFIC computations.
                if gain<0 and b.sale.date>=config.us_person_since:
                    replacement=[t.id for t in txs if t.type in ('BUY','REINVEST') and t.id!=b.buy.id and abs((t.date-b.sale.date).days)<=30]
                    if b.units<b.buy.units and abs((b.buy.date-b.sale.date).days)<=30:
                        replacement.append(b.buy.id+' (other shares in same acquisition)')
                    if replacement:
                        raise InputError(f'{b.sale.id}: loss with potential replacement acquisitions {replacement}; reviewed wash-sale basis required')
                if year==config.tax_year and b.sale.date>=config.us_person_since:
                    if b.sale.date<config.effective_pfic_start:
                        works.append({'kind':'sale','transaction_id':b.sale.id,'date':b.sale.date,
                                      'regime':'pre_PFIC','form_part':'capital_outside_8621',
                                      'proceeds_usd':proceeds,'adjusted_basis_usd':general_basis,
                                      'capital_gain_usd':max(ZERO,gain),'other_loss':max(ZERO,-gain),'tax':None})
                    elif mode in ('1291','transition'):
                        tax=section1291(gain,b.buy.date,b.sale.date,config.first_pfic_year,config.due_dates,pfic_start_date=config.effective_pfic_start) if gain>0 else None
                        works.append({'kind':'sale','transaction_id':b.sale.id,'date':b.sale.date,'regime':mode,'form_part':'V','proceeds_usd':proceeds,'adjusted_basis_usd':basis,'15f':gain,'tax':tax,'other_loss':max(ZERO,-gain)})
                    else:
                        works.append({'kind':'sale','transaction_id':b.sale.id,'date':b.sale.date,'regime':mode,'form_part':'IV',**residency_mtm_sale(general_basis,basis,proceeds,unreversed)})
                history.append({'year':year,'action':'sale','basis':general_basis,'mtm_basis_usd':basis,'us_taxable_event':b.sale.date>=config.us_person_since,'proceeds_usd':proceeds,'gain_usd':gain,'unreversed_inclusions':unreversed})
            alive=b.sale is None or b.sale.date.year>year
            if alive and mode in ('mtm','transition') and year>=config.us_person_since.year:
                valuation=config.valuations.get(year)
                if valuation is None:raise InputError(f'Year-end unit valuation required for {year}')
                fmv=fx.usd(valuation.unit_value*b.units,valuation.currency,date(year,12,31))
                old_basis=basis
                if mode=='transition':
                    gain=max(ZERO,fmv-basis);basis+=gain;general_basis+=gain;unreversed+=gain
                    record={'year':year,'kind':'mtm_transition','date':date(year,12,31),'form_part':'V','15f':gain,'fair_market_value_usd':fmv,'opening_basis':old_basis,'ending_basis':basis,'ending_unreversed':unreversed,'unrecognized_decline':max(ZERO,old_basis-fmv)}
                    if year==config.tax_year:
                        record['tax']=section1291(gain,b.buy.date,date(year,12,31),config.first_pfic_year,config.due_dates,pfic_start_date=config.effective_pfic_start) if gain else None
                        works.append(record)
                else:
                    record={'year':year,'kind':'mtm_year_end','form_part':'IV',**mtm_year_end(basis,fmv,unreversed)}
                    basis=record['ending_basis'];general_basis+=record['ordinary_income'];unreversed=record['ending_unreversed']
                    if year==config.tax_year:works.append(record)
                record['general_ending_basis_usd']=general_basis
                history.append(record)
        output.append({'block_id':b.id,'purchase_id':b.buy.id,'account':b.buy.account,'acquisition_date':b.buy.date,'holding_start':b.buy.date+timedelta(days=1),'units':b.units,'purchase_currency':b.buy.currency,'allocated_purchase_cost_local':b.purchase_cost,'original_basis_usd':original_basis,'sale_id':b.sale.id if b.sale else None,'sale_date':b.sale.date if b.sale else None,'allocated_net_proceeds_local':b.proceeds,'ending_basis_usd':general_basis if b.sale is None else ZERO,'ending_mtm_basis_usd':basis if b.sale is None else ZERO,'effective_pfic_start':config.effective_pfic_start,'pre_residency_acquisition':pre_residency,'ending_unreversed_inclusions':unreversed if b.sale is None else ZERO,'worksheets':works,'basis_history':history,'distribution_history':dist_history})
    # Summary values are derived from the very same worksheet values, not recomputed.
    summary={'1291_current_ordinary_income':ZERO,'1291_tax_before_credits':ZERO,'1291_credit':ZERO,'1291_additional_tax':ZERO,'1291_interest':Decimal(0),'ordinary_dividends':ZERO,'mtm_ordinary_income':ZERO,'other_losses_before_general_limitations':ZERO,'capital_gains_before_general_limitations':ZERO}
    with localcontext() as ctx:
        ctx.prec=80
        for b in output:
            for w in b['worksheets']:
                if w.get('tax'):
                    for target,line in [('1291_current_ordinary_income','16b'),('1291_tax_before_credits','16c'),('1291_credit','16d'),('1291_additional_tax','16e'),('1291_interest','16f')]:summary[target]+=w['tax'][line]
                if w['kind']=='dividend':summary['ordinary_dividends']+=w['nonexcess_dividend_usd']
                summary['mtm_ordinary_income']+=w.get('ordinary_income',ZERO)
                summary['other_losses_before_general_limitations']+=w.get('other_loss',ZERO)
                summary['capital_gains_before_general_limitations']+=w.get('capital_gain_usd',ZERO)
    report={'schema_version':'1.1','reporting_rounding':'whole dollars, half up, only at output','fund_name':config.fund_name,'tax_year':config.tax_year,'form_revision':'12/2025' if config.tax_year>=2025 else '12/2018','status':'calculation_worksheets_not_a_complete_signed_return','config':config,'ending_units':held,'blocks':output,'summary_usd':summary,'fx_audit':fx.audit,'interest_sources':__import__('pfic.tax',fromlist=['interest_schedule']).interest_schedule()['sources'],'benchmark_status':'Known differences from supplied Andrew Mitchel examples; see docs/benchmark_comparison.json and docs/VALIDATION.md', 'notes':['One uninterrupted U.S.-person period is modeled; pre-residency transactions remain in FIFO/history but are not current U.S. income events. Nonresident U.S.-source/ECI taxation, treaty overrides and repeated residency changes are outside this calculator.','Capital gains from dual-basis residency MTM sales are reported separately; complete capital-gain reporting outside Form 8621.','External benchmark differences remain disclosed; these worksheets have not been independently certified for filing.','Confirmation dates are treated as acquisition/disposition dates under the selected input policy. Verify they represent the tax-effective transaction dates.','Treasury quarterly rates are the user-selected approximation, not a claim that quarterly rates equal daily spot rates.','Part V annual dividend totals repeat across event worksheets; do not add those repeated totals.','Other losses are unnetted and subject to general capital loss, wash sale and other limitations outside this calculator.','Fund identity, ownership percentages, taxpayer identity, elections and filing exceptions require completion outside these calculation worksheets.']}
    return report


def calculate_csv(path,config,fx=None):
    report=calculate(read_csv(path),config,fx)
    report['input_sha256']=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    report['input_filename']=Path(path).name
    return report
