"""Pure §1291 and §1296 primitives, independent of CSV and network."""
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import lru_cache
import calendar
import json
from pathlib import Path
from .numbers import Q, dec, InputError
from .model import day

@lru_cache(maxsize=1)
def interest_schedule():
    return json.loads((Path(__file__).parent/'data'/'interest_rates.json').read_text())

def highest_individual_rate(year):
    for lo,hi,value in [(1987,1987,'0.385'),(1988,1990,'0.28'),(1991,1992,'0.31'),(1993,2000,'0.396'),(2001,2001,'0.391'),(2002,2002,'0.386'),(2003,2012,'0.35'),(2013,2017,'0.396'),(2018,2025,'0.37')]:
        if lo<=year<=hi:return Q(value)
    raise InputError(f'No verified highest individual tax rate for {year}')

def holding_days(acquired,event):
    """Exclude acquisition; include disposition/distribution. No timezone arithmetic."""
    acquired,event=day(acquired),day(event)
    if event<=acquired:
        raise InputError('Same-day or earlier distribution/disposition needs an explicitly reviewed holding-period rule')
    result={}
    cursor=acquired+timedelta(days=1)
    while cursor<=event:
        end=min(date(cursor.year,12,31),event)
        result[cursor.year]=(end-cursor).days+1
        cursor=end+timedelta(days=1)
    return result

def compound_factor(annual_rate, days, year_days):
    if type(days) is not int or days < 0 or year_days not in (365,366):
        raise InputError('Invalid compound-interest interval')
    with localcontext() as ctx:
        ctx.prec=80
        return (Decimal(1)+dec(Q(annual_rate))/year_days)**days

@lru_cache(maxsize=1024)
def interest_factor(start,end):
    """[start, end), daily compounding at annual rate / actual days in year."""
    start,end=day(start),day(end)
    if end<start:raise InputError('Interest end before start')
    trace=[]
    with localcontext() as ctx:
        ctx.prec=80
        balance=Decimal(1);cursor=start
        rates=interest_schedule()['annual_percent']
        while cursor<end:
            qmonth=((cursor.month-1)//3)*3+1
            key=f'{cursor.year}-{qmonth:02d}-01'
            if key not in rates:raise InputError(f'No verified IRS interest rate for {key}')
            boundary=date(cursor.year+1,1,1) if qmonth==10 else date(cursor.year,qmonth+3,1)
            stop=min(end,boundary)
            days=(stop-cursor).days
            annual=Decimal(rates[key])/100
            denominator=366 if calendar.isleap(cursor.year) else 365
            factor=compound_factor(annual,days,denominator)
            balance*=factor
            trace.append({'start_inclusive':cursor,'end_exclusive':stop,'days':days,'annual_rate':Q(annual),'year_days':denominator,'factor':factor})
            cursor=stop
        return balance-1,tuple(trace)

def section1291(amount_usd, acquired, event, first_pfic_year, due_dates, credit_usd=0):
    amount,credit=Q(amount_usd),Q(credit_usd)
    if amount<0 or credit<0:raise InputError('§1291 excess and credit cannot be negative')
    event=day(event);days=holding_days(acquired,event);total=sum(days.values())
    rows=[];ordinary=Q(0);tax=Q(0);used_credit=Q(0);current_credit=Q(0);interest=Decimal(0)
    with localcontext() as ctx:
        ctx.prec=80
        for year,count in days.items():
            allocation=amount*count/total;allocated_credit=credit*count/total
            deferred=first_pfic_year<=year<event.year
            gross=allocation*highest_individual_rate(year) if deferred else Q(0)
            used=min(gross,allocated_credit) if deferred else Q(0)
            net=gross-used;charge=Decimal(0);segments=()
            if net:
                if year not in due_dates or event.year not in due_dates:
                    raise InputError(f'Unextended return due dates required for tax years {year} and {event.year}; supply Config.due_dates')
                factor,segments=interest_factor(day(due_dates[year]),day(due_dates[event.year]))
                charge=dec(net)*factor
            if not deferred:ordinary+=allocation;current_credit+=allocated_credit
            tax+=gross;used_credit+=used;interest+=charge
            rows.append({'year':year,'days':count,'allocated_excess_usd':allocation,'category':'prior_PFIC' if deferred else ('current' if year==event.year else 'pre_PFIC'),'highest_tax_rate':highest_individual_rate(year) if deferred else None,'gross_tax':gross,'allocated_credit':allocated_credit,'credit_used':used,'net_tax':net,'interest':charge,'interest_segments':segments})
    return {'holding_start':day(acquired)+timedelta(days=1),'holding_end':event,'holding_days':total,'amount_usd':amount,'annual_allocations':rows,'16b':ordinary,'16c':tax,'16d':used_credit,'16e':tax-used_credit,'16f':interest,'current_year_credit_candidate':current_credit}

def mtm_year_end(basis,fmv,unreversed):
    basis,fmv,unreversed=map(Q,(basis,fmv,unreversed))
    if min(basis,fmv,unreversed)<0:raise InputError('Negative MTM state')
    difference=fmv-basis
    recognized=difference if difference>=0 else -min(-difference,unreversed)
    return {'10a':fmv,'10b':basis,'10c':difference,'11':unreversed if difference<0 else None,'12':-recognized if recognized<0 else Q(0),'ordinary_income':recognized,'ending_basis':basis+recognized,'ending_unreversed':unreversed+recognized,'unrecognized_decline':max(Q(0),-difference+recognized)}

def mtm_sale(basis,proceeds,unreversed):
    basis,proceeds,unreversed=map(Q,(basis,proceeds,unreversed))
    if min(basis,proceeds,unreversed)<0:raise InputError('Negative MTM sale state')
    gain=proceeds-basis;ordinary=gain if gain>=0 else -min(-gain,unreversed)
    return {'13a':proceeds,'13b':basis,'13c':gain,'14a':unreversed if gain<0 else None,'14b':-ordinary if ordinary<0 else Q(0),'14c':max(Q(0),-gain+ordinary),'ordinary_income':ordinary,'other_loss':max(Q(0),-gain+ordinary)}


def distribution_excess(current_total,prior_included_total,preceding_years):
    """Annual threshold in one calculation currency. Prior total excludes the
    §1291 excess portions not included in gross income (prior-PFIC allocations).
    """
    current,prior=Q(current_total),Q(prior_included_total)
    if current<0 or prior<0 or type(preceding_years) is not int or not 0<=preceding_years<=3:
        raise InputError('Invalid distribution threshold inputs')
    average=prior/preceding_years if preceding_years else Q(0)
    threshold=average*Q('1.25')
    excess=max(Q(0),current-threshold) if preceding_years else Q(0)
    return {'15a':current,'15b':prior,'15c':average,'15d':threshold,'excess':excess,'nonexcess':current-excess}
